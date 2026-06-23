import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ats_simulator import extract_pdf_text
from core.html_reporter import REPORTS_ROOT, generate_cover_letter_report, slugify


FORBIDDEN_PHRASES = [
    "sou apaixonado por tecnologia",
    "me identifico com os valores",
    "estou pronto para novos desafios",
    "tenho facilidade para trabalhar em equipe",
    "busco uma oportunidade",
    "i am passionate",
    "team player",
]


@dataclass
class CoverLetterResult:
    carta: str
    idioma: str
    word_count: int
    avisos: list[str]
    html_path: Path


_PROMPT = """
Voce e um redator senior de cartas de apresentacao para vagas de tecnologia,
com criterio de recrutador tecnico. Escreva como um senior: especifico, sobrio,
direto, sem frases genericas e sem prometer o que o curriculo nao prova.

## PERFIL DETALHADO DO USUARIO
{profile_text}

## TEXTO BRUTO EXTRAIDO DO CURRICULO PDF
{resume_text}

## VAGA
Titulo: {job_title}
Empresa: {job_company}
Descricao:
{job_description}

## TAREFA
Escreva uma carta de apresentacao contextualizada para esta vaga.

Retorne SOMENTE JSON valido, sem markdown e sem texto extra:

{{
  "carta": "<texto completo da carta>",
  "idioma": "pt-BR|en-US"
}}

## REGRAS
- Pense como senior: conecte evidencia real do perfil aos requisitos mais importantes da vaga.
- Detecte o idioma da vaga e escreva a carta no mesmo idioma.
- Limite a carta a 250 palavras.
- Use tres partes naturais: abertura, meio e fechamento.
- Abertura: mencione algo especifico da empresa ou da vaga, nunca generico.
- Meio: conecte 1 a 2 experiencias reais do candidato com o que a vaga pede.
- Fechamento: use call to action direto.
- Nao invente experiencia, cargo, senioridade, certificacao, projeto, formacao ou tecnologia.
- Se uma experiencia ou skill nao aparecer no perfil/curriculo, nao diga que o candidato tem.
- Nao use frases genericas ou proibidas.

## FRASES PROIBIDAS
{forbidden_phrases}
"""


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(_escape_control_chars_in_strings(stripped))
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        payload = match.group()
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return json.loads(_escape_control_chars_in_strings(payload))

    raise ValueError(f"JSON invalido na resposta da carta: {text[:300]}")


def _escape_control_chars_in_strings(text: str) -> str:
    """Recover JSON where the model placed literal line breaks inside strings."""
    chars = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                chars.append(char)
                escaped = False
                continue
            if char == "\\":
                chars.append(char)
                escaped = True
                continue
            if char == '"':
                chars.append(char)
                in_string = False
                continue
            if char == "\n":
                chars.append("\\n")
                continue
            if char == "\r":
                chars.append("\\r")
                continue
            if char == "\t":
                chars.append("\\t")
                continue
            if ord(char) < 0x20:
                chars.append(f"\\u{ord(char):04x}")
                continue
            chars.append(char)
            continue

        chars.append(char)
        if char == '"':
            in_string = True

    return "".join(chars)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text, flags=re.UNICODE))


def _mark_forbidden_phrases(letter: str) -> tuple[str, list[str]]:
    warnings = []
    marked = letter
    for phrase in FORBIDDEN_PHRASES:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        if pattern.search(marked):
            warnings.append(f"Frase proibida encontrada: {phrase}")
            marked = pattern.sub(lambda match: f"[REVISAR] {match.group(0)}", marked)
    return marked, warnings


def generate_cover_letter_text(
    profile_text: str,
    resume_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
) -> dict[str, Any]:
    from groq import Groq

    client = Groq(api_key=groq_api_key)
    prompt = _PROMPT.format(
        profile_text=(profile_text or "")[:12000],
        resume_text=(resume_text or "")[:12000],
        job_title=job_title or "Nao informado",
        job_company=job_company or "Nao informada",
        job_description=job_description[:7000],
        forbidden_phrases="\n".join(f"- {phrase}" for phrase in FORBIDDEN_PHRASES),
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON. Escape line breaks inside string values as \\n. No markdown, no explanation.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.4,
        max_tokens=1200,
    )
    data = _extract_json(response.choices[0].message.content or "")
    return {
        "carta": str(data.get("carta", "")).strip(),
        "idioma": str(data.get("idioma", "")).strip() or "pt-BR",
    }


def create_cover_letter_for_job(
    profile_text: str,
    resume_pdf_path: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    open_browser: bool = True,
) -> CoverLetterResult:
    extraction = extract_pdf_text(resume_pdf_path)
    generated = generate_cover_letter_text(
        profile_text=profile_text,
        resume_text=extraction.text,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description,
        groq_api_key=groq_api_key,
        model_name=model_name,
    )

    letter, warnings = _mark_forbidden_phrases(generated["carta"])
    word_count = _word_count(letter)
    if word_count > 250:
        warnings.append(f"Carta com {word_count} palavras; revise para ficar no limite de 250 palavras.")
    if extraction.warnings:
        warnings.extend(f"PDF: {warning}" for warning in extraction.warnings)

    title = job_title or "Vaga analisada"
    company = job_company or "Empresa nao informada"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = slugify(f"carta-{stamp}-{company}-{title}")
    payload = {
        "title": f"Carta - {title}" if not job_company else f"Carta - {title} @ {job_company}",
        "carta": letter,
        "idioma": generated["idioma"] if generated["idioma"] in {"pt-BR", "en-US"} else "pt-BR",
        "word_count": word_count,
        "avisos": warnings,
    }
    html_path = generate_cover_letter_report(payload, filename, open_browser=open_browser)
    try:
        html_report = str(html_path.relative_to(REPORTS_ROOT))
    except ValueError:
        html_report = str(html_path)

    (REPORTS_ROOT / f"{filename}.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "type": "cover_letter",
                "job": {
                    "title": job_title or "Nao informado",
                    "company": job_company or "Nao informada",
                    "description": job_description,
                },
                "letter": payload,
                "html_report": html_report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return CoverLetterResult(
        carta=letter,
        idioma=payload["idioma"],
        word_count=word_count,
        avisos=warnings,
        html_path=html_path,
    )
