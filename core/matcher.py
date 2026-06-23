import json
import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MatchResult:
    score: int
    pontos_fortes: list[str]
    gaps: list[str]
    resumo: str
    curriculo_foco: list[str]
    curriculo_ajustes: list[str]
    curriculo_headline: str


_PROMPT = """
Voce e um recrutador senior especializado em tecnologia, com criterio de hiring manager,
analisando candidatos para vagas de forma realista, conservadora e orientada a evidencias.

## PERFIL DO CANDIDATO
{profile}

## VAGA
Titulo: {job_title}
Empresa: {job_company}
Descricao:
{job_description}

## TAREFA
Analise a compatibilidade e retorne SOMENTE JSON valido, sem markdown, sem texto extra:

{{
  "score": <0-100>,
  "pontos_fortes": ["<ponto especifico e concreto 1>", "<ponto 2>", "<ponto 3>"],
  "gaps": ["<gap real 1>", "<gap real 2>"],
  "resumo": "<1 frase objetiva explicando o score>",
  "curriculo_foco": ["<habilidade/experiencia real que deve aparecer primeiro no curriculo>", "<outro foco>"],
  "curriculo_ajustes": ["<ajuste profissional e honesto para aproximar o curriculo da vaga>", "<outro ajuste>"],
  "curriculo_headline": "<headline/resumo de 1 frase para um curriculo direcionado a esta vaga>"
}}

## CRITERIOS DE SCORE
- 90-100: Fit perfeito, atende todos os requisitos principais e secundarios
- 80-89: Forte compatibilidade, 1-2 gaps menores facilmente superaveis
- 70-79: Boa base, mas gaps relevantes que precisariam de justificativa na entrevista
- 60-69: Compatibilidade parcial, falta algo importante
- <60: Baixa compatibilidade

## INSTRUCOES IMPORTANTES
- Seja criterioso e realista; nao infle o score.
- Se a vaga nao especificar tecnologias, avalie pela area geral.
- Gaps so devem aparecer se forem requisitos explicitos da vaga que o candidato nao tem.
- As recomendacoes de curriculo devem ser honestas: realce apenas experiencias, projetos e habilidades presentes no perfil do candidato.
- Nao mande o candidato inventar experiencia, cargo, senioridade, certificacao ou tecnologia.
- Escreva em portugues profissional.

REGRAS CONSERVADORAS:
- 90+ somente se a vaga for claramente junior/estagio/trainee, tiver area/stack alinhada e requisitos principais atendidos.
- Vaga pleno/senior deve ficar abaixo de 70, salvo se aceitar explicitamente junior.
- Stack principal Node, Python, C#, .NET, PHP, mobile, frontend ou dados deve ficar no maximo em 55 quando o perfil nao for dessa area.
- Sem stack/area explicita alinhada, score maximo 60.
- Pagina agregada/listagem generica, score maximo 45.
- Nao recompense tecnologias que o candidato nao conhece.
"""


_BATCH_PROMPT = """
Voce e um recrutador senior especializado em tecnologia, com criterio de hiring manager.
Sua tarefa e comparar o mesmo perfil/curriculo contra varias vagas em uma unica analise,
economizando tokens sem perder criterio.

## PERFIL DO CANDIDATO
{profile}

## VAGAS PARA ANALISAR
{jobs_json}

## TAREFA
Analise cada vaga separadamente contra o perfil do candidato.
Retorne SOMENTE JSON valido, sem markdown, sem texto extra:

{{
  "matches": [
    {{
      "id": "<id recebido da vaga>",
      "score": <0-100>,
      "pontos_fortes": ["<ponto especifico e concreto 1>", "<ponto 2>", "<ponto 3>"],
      "gaps": ["<gap real 1>", "<gap real 2>"],
      "resumo": "<1 frase objetiva explicando o score>",
      "curriculo_foco": ["<habilidade/experiencia real que deve aparecer primeiro no curriculo>"],
      "curriculo_ajustes": ["<ajuste profissional e honesto para aproximar o curriculo da vaga>"],
      "curriculo_headline": "<headline/resumo de 1 frase para um curriculo direcionado a esta vaga>"
    }}
  ]
}}

## CRITERIOS DE SCORE
- 90-100: Fit perfeito, atende todos os requisitos principais e secundarios.
- 80-89: Forte compatibilidade, 1-2 gaps menores facilmente superaveis.
- 70-79: Boa base, mas gaps relevantes que precisariam de justificativa na entrevista.
- 60-69: Compatibilidade parcial, falta algo importante.
- <60: Baixa compatibilidade.

## REGRAS SENIOR
- Avalie cada vaga individualmente. Nao misture requisitos entre vagas.
- Seja criterioso e realista; nao infle score para agradar.
- Gaps devem ser requisitos explicitos da vaga que nao aparecem no perfil.
- Recomendacoes devem ser honestas: realce apenas experiencias, projetos e habilidades presentes no perfil.
- Nao invente experiencia, cargo, senioridade, certificacao, formacao, empresa, projeto ou tecnologia.
- Se uma vaga for vaga senior/pleno/lead e o perfil nao evidenciar isso, limite o score e explique.
- Score 90+ somente quando a vaga for claramente junior/estagio/trainee, tiver area/stack alinhada e requisitos principais atendidos.
- Stack principal Node, Python, C#, .NET, PHP, mobile, frontend ou dados deve ficar no maximo em 55 quando o perfil nao for dessa area.
- Sem stack/area explicita alinhada, score maximo 60.
- Pagina agregada/listagem generica, score maximo 45.
- Escreva em portugues profissional.
"""


def _norm(text: str) -> str:
    return text.casefold()


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _apply_score_caps(result: MatchResult, job_title: str, job_description: str) -> MatchResult:
    text = _norm(f"{job_title}\n{job_description}")
    cap = 100
    extra_gaps = []

    is_entry = _contains_any(text, [
        "junior", "junior", "jr", "estagio", "estagio", "estagiario",
        "estagiario", "trainee", "entry level", "entry-level",
    ])
    is_mid_senior = _contains_any(text, [
        "pleno", "senior", "senior", "sr ", "especialista", "staff",
        "principal", "tech lead", "lead ",
    ])
    generic_listing = _contains_any(text, [
        "+ de ", "1.000+", "vagas de ", "vagas em ", "jobs in ",
    ])

    if generic_listing:
        cap = min(cap, 45)
        extra_gaps.append("Resultado parece uma pagina/listagem generica, nao uma vaga individual.")
    if is_mid_senior and not is_entry:
        cap = min(cap, 68)
        extra_gaps.append("Senioridade parece acima de junior/estagio/trainee.")
    if result.score >= 90 and not is_entry:
        cap = min(cap, 84)
        extra_gaps.append("Score 90+ exige vaga claramente junior/estagio/trainee.")

    if result.score > cap:
        result.score = cap
        result.resumo = f"{result.resumo} Score limitado por regras conservadoras."

    for gap in extra_gaps:
        if gap not in result.gaps:
            result.gaps.append(gap)

    return result


def calculate_local_match(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
) -> MatchResult:
    text = f"{job_title}\n{job_company}\n{job_description}".casefold()

    positives = {
        "java": 14,
        "spring": 12,
        "spring boot": 14,
        "backend": 8,
        "back-end": 8,
        "api": 5,
        "rest": 5,
        "sql": 4,
        "postgres": 4,
        "postgresql": 4,
        "docker": 3,
        "redis": 3,
        "junior": 6,
        "jr": 6,
        "estagio": 6,
        "estagiario": 6,
        "trainee": 6,
        "remoto": 3,
        "home office": 3,
    }
    negatives = {
        "senior": 18,
        "pleno": 10,
        "python": 8,
        "node": 8,
        "c#": 8,
        ".net": 8,
        "php": 8,
        "mobile": 8,
        "ios": 8,
        "android": 8,
    }

    matched = [term for term in positives if term in text]
    penalties = [term for term in negatives if term in text]
    score = 25 + sum(positives[term] for term in matched) - sum(negatives[term] for term in penalties)

    if "java" not in text and "spring" not in text:
        score -= 20
    if "backend" not in text and "back-end" not in text and "desenvolvedor" not in text:
        score -= 10

    score = max(0, min(82, score))
    pontos = [f"Vaga menciona {term}" for term in matched[:4]] or ["Vaga relacionada a desenvolvimento de software"]
    gaps = [f"Termo pode indicar desalinhamento: {term}" for term in penalties[:3]]

    result = MatchResult(
        score=score,
        pontos_fortes=pontos,
        gaps=gaps,
        resumo="Score local por palavras-chave porque a IA nao respondeu nesta varredura.",
        curriculo_foco=pontos[:3],
        curriculo_ajustes=[
            "Coloque no resumo profissional as tecnologias que aparecem na vaga e ja existem no seu perfil.",
            "Priorize projetos e experiencias mais parecidos com os requisitos da vaga.",
            "Use bullets com resultado, tecnologia e impacto, sem adicionar habilidades que voce nao tem.",
        ],
        curriculo_headline=f"Profissional de desenvolvimento com foco alinhado a {job_title}.",
    )
    return _apply_score_caps(result, job_title, job_description)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"JSON invalido na resposta: {text[:300]}")


def _coerce_score(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return 0


def _as_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def calculate_match(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    use_local_fallback: bool = True,
) -> Optional[MatchResult]:
    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)

        prompt = _PROMPT.format(
            profile=profile_text,
            job_title=job_title,
            job_company=job_company,
            job_description=job_description[:2500],
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=900,
        )

        data = _extract_json(response.choices[0].message.content or "")

        result = MatchResult(
            score=int(data.get("score", 0)),
            pontos_fortes=_as_list(data.get("pontos_fortes")),
            gaps=_as_list(data.get("gaps")),
            resumo=str(data.get("resumo", "")),
            curriculo_foco=_as_list(data.get("curriculo_foco")),
            curriculo_ajustes=_as_list(data.get("curriculo_ajustes")),
            curriculo_headline=str(data.get("curriculo_headline", "")),
        )
        return _apply_score_caps(result, job_title, job_description)

    except Exception as e:
        print(f"[Matcher] Erro: {e}")
        if not use_local_fallback:
            return None
        return calculate_local_match(
            profile_text=profile_text,
            job_title=job_title,
            job_company=job_company,
            job_description=job_description,
        )


def calculate_matches_batch(
    profile_text: str,
    jobs: list[Any],
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    use_local_fallback: bool = True,
) -> dict[str, MatchResult]:
    """Analyze many jobs in one LLM call and return results keyed by job id."""
    prepared_jobs = []
    job_by_id = {}
    for index, job in enumerate(jobs, start=1):
        job_id = str(getattr(job, "id", "") or f"job-{index}")
        job_by_id[job_id] = job
        prepared_jobs.append({
            "id": job_id,
            "title": getattr(job, "title", "") or "",
            "company": getattr(job, "company", "") or "",
            "location": getattr(job, "location", "") or "",
            "source": getattr(job, "source", "") or "",
            "description": (getattr(job, "description", "") or "")[:1600],
        })

    if not prepared_jobs:
        return {}

    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)
        prompt = _BATCH_PROMPT.format(
            profile=profile_text[:12000],
            jobs_json=json.dumps(prepared_jobs, ensure_ascii=False),
        )
        max_tokens = max(1200, min(7000, 450 + len(prepared_jobs) * 520))
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON. No markdown, no explanation. "
                        "You are a senior technical recruiter and must be conservative."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        data = _extract_json(response.choices[0].message.content or "")
        raw_matches = data.get("matches", [])
        if not isinstance(raw_matches, list):
            raise ValueError("Resposta em lote sem lista matches.")

        results: dict[str, MatchResult] = {}
        for item in raw_matches:
            if not isinstance(item, dict):
                continue
            job_id = str(item.get("id", "")).strip()
            job = job_by_id.get(job_id)
            if not job:
                continue
            result = MatchResult(
                score=_coerce_score(item.get("score", 0)),
                pontos_fortes=_as_list(item.get("pontos_fortes")),
                gaps=_as_list(item.get("gaps")),
                resumo=str(item.get("resumo", "")).strip(),
                curriculo_foco=_as_list(item.get("curriculo_foco")),
                curriculo_ajustes=_as_list(item.get("curriculo_ajustes")),
                curriculo_headline=str(item.get("curriculo_headline", "")).strip(),
            )
            results[job_id] = _apply_score_caps(result, getattr(job, "title", ""), getattr(job, "description", ""))

        missing_ids = [job_id for job_id in job_by_id if job_id not in results]
        if missing_ids and not use_local_fallback:
            print(f"[MatcherBatch] IA nao retornou {len(missing_ids)} vaga(s).")
        if use_local_fallback:
            for job_id in missing_ids:
                job = job_by_id[job_id]
                results[job_id] = calculate_local_match(
                    profile_text=profile_text,
                    job_title=getattr(job, "title", ""),
                    job_company=getattr(job, "company", ""),
                    job_description=getattr(job, "description", ""),
                )
        return results

    except Exception as e:
        print(f"[MatcherBatch] Erro: {e}")
        if not use_local_fallback:
            return {}
        return {
            job_id: calculate_local_match(
                profile_text=profile_text,
                job_title=getattr(job, "title", ""),
                job_company=getattr(job, "company", ""),
                job_description=getattr(job, "description", ""),
            )
            for job_id, job in job_by_id.items()
        }
