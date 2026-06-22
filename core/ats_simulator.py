import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.html_reporter import REPORTS_ROOT, generate_ats_report, slugify


@dataclass
class PdfExtraction:
    text: str
    warnings: list[str]
    page_count: int


@dataclass
class AtsSimulation:
    coverage_score: int
    risk: str
    diagnostico: str
    keywords_presentes: list[str]
    keywords_ausentes: list[str]
    avisos_pdf: list[str]
    raw_resume_text: str
    html_path: Path


_PROMPT = """
Voce e um especialista em ATS e recrutamento tecnico.

## TEXTO BRUTO EXTRAIDO DO CURRICULO
{resume_text}

## VAGA
Titulo: {job_title}
Empresa: {job_company}
Descricao:
{job_description}

## TAREFA
Extraia todas as tecnologias, ferramentas, metodologias e certificacoes mencionadas na vaga.
Para cada item, diga se ele aparece claramente no texto bruto do curriculo.

Retorne SOMENTE JSON valido, sem markdown e sem texto extra:

{{
  "coverage_score": <0-100>,
  "diagnostico": "<1 frase objetiva em portugues>",
  "keywords_presentes": ["<keyword encontrada no curriculo>"],
  "keywords_ausentes": ["<keyword ausente no curriculo>"]
}}

## REGRAS
- Nao conte como presente uma keyword que nao aparece no curriculo ou que aparece de forma ambigua.
- Agrupe variacoes obvias, como "PostgreSQL" e "Postgres".
- Foque em tecnologias, ferramentas, metodologias, certificacoes, idiomas tecnicos e requisitos objetivos.
- Nao inclua beneficios, responsabilidades genericas ou soft skills vagas.
- Seja conservador no percentual.
"""


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"JSON invalido na resposta ATS: {text[:300]}")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _risk_from_score(score: int) -> str:
    if score > 70:
        return "baixo"
    if score >= 50:
        return "medio"
    return "alto"


def extract_pdf_text(pdf_path: str) -> PdfExtraction:
    path = Path(pdf_path or "")
    if not path.exists():
        raise FileNotFoundError("Curriculo PDF nao encontrado. Configure o arquivo em Configurar.")
    if path.suffix.lower() != ".pdf":
        raise ValueError("O curriculo configurado precisa ser um arquivo PDF.")

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF nao esta instalado. Rode pip install PyMuPDF.") from exc

    warnings = []
    page_texts = []
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            stripped = text.strip()
            if len(stripped) < 50:
                warnings.append(
                    f"Pagina {index} tem menos de 50 caracteres extraidos; pode ser imagem ou pouco legivel para ATS."
                )
            page_texts.append(text)

    full_text = "\n\n".join(page_texts).strip()
    if len(full_text) < 300:
        warnings.append("Texto total extraido tem menos de 300 caracteres; o PDF pode estar vazio, escaneado ou corrompido para ATS.")

    blank_clusters = len(re.findall(r"(?:\n\s*){4,}", full_text))
    short_lines = [line for line in full_text.splitlines() if 0 < len(line.strip()) <= 18]
    total_lines = [line for line in full_text.splitlines() if line.strip()]
    if blank_clusters >= 3 or (total_lines and len(short_lines) / len(total_lines) > 0.45):
        warnings.append("O texto extraido tem muitas quebras/linhas curtas; curriculo em colunas pode ser lido fora de ordem pelo ATS.")

    return PdfExtraction(text=full_text, warnings=warnings, page_count=len(page_texts))


def analyze_ats_keywords(
    resume_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
) -> dict:
    from groq import Groq

    client = Groq(api_key=groq_api_key)
    prompt = _PROMPT.format(
        resume_text=resume_text[:16000],
        job_title=job_title or "Nao informado",
        job_company=job_company or "Nao informada",
        job_description=job_description[:7000],
    )
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1200,
    )
    data = _extract_json(response.choices[0].message.content or "")
    score = max(0, min(100, int(data.get("coverage_score", 0) or 0)))
    return {
        "coverage_score": score,
        "diagnostico": str(data.get("diagnostico", "")).strip() or "Diagnostico nao informado.",
        "keywords_presentes": _as_list(data.get("keywords_presentes")),
        "keywords_ausentes": _as_list(data.get("keywords_ausentes")),
    }


def simulate_ats_for_job(
    resume_pdf_path: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    open_browser: bool = True,
) -> AtsSimulation:
    extraction = extract_pdf_text(resume_pdf_path)
    analysis = analyze_ats_keywords(
        extraction.text,
        job_title,
        job_company,
        job_description,
        groq_api_key,
        model_name=model_name,
    )

    score = analysis["coverage_score"]
    risk = _risk_from_score(score)
    title = job_title or "Vaga analisada"
    company = job_company or "Empresa nao informada"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = slugify(f"ats-{stamp}-{company}-{title}")
    payload = {
        "title": f"ATS - {title}" if not job_company else f"ATS - {title} @ {job_company}",
        "coverage_score": score,
        "risk": risk,
        "diagnostico": analysis["diagnostico"],
        "keywords_presentes": analysis["keywords_presentes"],
        "keywords_ausentes": analysis["keywords_ausentes"],
        "avisos_pdf": extraction.warnings,
    }
    html_path = generate_ats_report(payload, filename, open_browser=open_browser)
    json_path = REPORTS_ROOT / f"{filename}.json"
    try:
        html_report = str(html_path.relative_to(REPORTS_ROOT))
    except ValueError:
        html_report = str(html_path)
    json_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "type": "ats_simulation",
                "job": {
                    "title": job_title or "Nao informado",
                    "company": job_company or "Nao informada",
                    "description": job_description,
                },
                "analysis": payload,
                "html_report": html_report,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return AtsSimulation(
        coverage_score=score,
        risk=risk,
        diagnostico=analysis["diagnostico"],
        keywords_presentes=analysis["keywords_presentes"],
        keywords_ausentes=analysis["keywords_ausentes"],
        avisos_pdf=extraction.warnings,
        raw_resume_text=extraction.text,
        html_path=html_path,
    )
