import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SingleJobAnalysis:
    score: int
    veredito: str
    pontos_fortes: list[str]
    pontos_fracos: list[str]
    melhorias_curriculo: list[str]
    itens_menos_relevantes: list[str]
    prioridade_ajuste: str
    proxima_acao: str


_PROMPT = """
Voce e um consultor senior de carreira em tecnologia.

## PERFIL/CURRICULO ATUAL DO USUARIO
{profile}

## VAGA ESPECIFICA
Titulo: {job_title}
Empresa: {job_company}
Descricao:
{job_description}

## TAREFA
Analise somente esta vaga contra o perfil/curriculo atual do usuario.
Nao crie curriculo novo. Nao escreva uma versao final do curriculo.
Retorne somente orientacoes profissionais sobre o que melhorar, destacar,
reduzir ou verificar no curriculo atual para esta vaga.

Retorne SOMENTE JSON valido, sem markdown e sem texto extra:

{{
  "score": <0-100>,
  "veredito": "<1 frase objetiva sobre a compatibilidade>",
  "pontos_fortes": ["<forca real do usuario para esta vaga>", "<outra forca>"],
  "pontos_fracos": ["<gap real ou requisito nao evidenciado>", "<outro gap>"],
  "melhorias_curriculo": ["<melhoria objetiva no curriculo atual>", "<outra melhoria>"],
  "itens_menos_relevantes": ["<item que pode perder destaque para esta vaga>", "<outro item>"],
  "prioridade_ajuste": "alta|media|baixa",
  "proxima_acao": "<acao mais importante antes de se candidatar>"
}}

## REGRAS
- Seja profissional, especifico e honesto.
- Nao invente experiencia, cargo, senioridade, certificacao, projeto ou tecnologia.
- Se algo seria bom mas nao aparece no perfil, escreva como verificacao: "Se voce tiver X, deixe isso claro".
- Pontos fracos devem ser requisitos da vaga que nao aparecem claramente no perfil/curriculo.
- Melhorias devem dizer "melhore X" ou "deixe Y mais visivel", nao gerar o texto final do curriculo.
- Itens menos relevantes sao coisas que podem ocupar menos espaco nesta candidatura, nao coisas para apagar permanentemente.
- Use portugues profissional.
- Score 90+ somente quando os requisitos principais estao claramente atendidos.
- Se a vaga pede senioridade acima da evidenciada no perfil, limite o score e explique.
"""


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"JSON invalido na resposta: {text[:300]}")


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_priority(value: str) -> str:
    value = str(value or "").strip().casefold()
    if value in {"alta", "media", "baixa"}:
        return value
    return "media"


def calculate_local_single_job_analysis(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
) -> SingleJobAnalysis:
    text = f"{job_title}\n{job_company}\n{job_description}".casefold()
    profile = profile_text.casefold()

    important_terms = [
        "java", "spring", "spring boot", "python", "node", "react", "sql",
        "postgres", "docker", "aws", "api", "rest", "backend", "frontend",
        "dados", "power bi", "excel", "git",
    ]
    matched = [term for term in important_terms if term in text and term in profile]
    missing = [term for term in important_terms if term in text and term not in profile]

    score = 45 + len(matched) * 7 - len(missing) * 6
    if any(term in text for term in ["senior", "pleno", "lead", "especialista"]):
        score -= 12
    score = max(0, min(78, score))

    strengths = [f"O curriculo/perfil ja evidencia {term}, que aparece na vaga." for term in matched[:4]]
    if not strengths:
        strengths = ["Ha algum alinhamento geral com a area, mas faltam evidencias claras por palavra-chave."]

    gaps = [f"A vaga menciona {term}, mas isso nao aparece claramente no curriculo/perfil." for term in missing[:4]]

    return SingleJobAnalysis(
        score=score,
        veredito="Analise local por palavras-chave porque a IA nao respondeu nesta consulta.",
        pontos_fortes=strengths,
        pontos_fracos=gaps,
        melhorias_curriculo=[
            "Deixe mais visiveis no topo do curriculo as competencias que batem diretamente com a vaga.",
            "Priorize experiencias e projetos parecidos com os requisitos da vaga.",
            "Remova destaque de informacoes que nao ajudam nesta candidatura especifica.",
        ],
        itens_menos_relevantes=[
            "Experiencias muito distantes da stack ou area da vaga podem ocupar menos espaco.",
        ],
        prioridade_ajuste="media" if score >= 60 else "alta",
        proxima_acao="Revisar o resumo profissional e os primeiros bullets antes de se candidatar.",
    )


def analyze_single_job(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    use_local_fallback: bool = True,
) -> Optional[SingleJobAnalysis]:
    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)
        prompt = _PROMPT.format(
            profile=profile_text[:12000],
            job_title=job_title or "Nao informado",
            job_company=job_company or "Nao informada",
            job_description=job_description[:5000],
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        data = _extract_json(response.choices[0].message.content or "")

        return SingleJobAnalysis(
            score=max(0, min(100, int(data.get("score", 0)))),
            veredito=str(data.get("veredito", "")).strip(),
            pontos_fortes=_as_list(data.get("pontos_fortes")),
            pontos_fracos=_as_list(data.get("pontos_fracos")),
            melhorias_curriculo=_as_list(data.get("melhorias_curriculo")),
            itens_menos_relevantes=_as_list(data.get("itens_menos_relevantes")),
            prioridade_ajuste=_normalize_priority(data.get("prioridade_ajuste")),
            proxima_acao=str(data.get("proxima_acao", "")).strip(),
        )
    except Exception as exc:
        print(f"[SingleJobAnalyzer] Erro: {exc}")
        if not use_local_fallback:
            return None
        return calculate_local_single_job_analysis(profile_text, job_title, job_company, job_description)
