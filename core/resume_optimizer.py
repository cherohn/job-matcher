import json
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResumeOptimization:
    headline_sugerida: str
    resumo_profissional_sugerido: str
    skills_prioritarias: list[str]
    experiencias_prioritarias: list[str]
    bullets_sugeridos: list[str]
    reduzir_ou_remover: list[str]
    evidencias_ausentes: list[str]
    avisos_honestidade: list[str]
    proxima_acao: str


_PROMPT = """
Voce e um especialista senior em curriculos de tecnologia, com experiencia em triagem,
ATS, recrutamento tecnico e posicionamento de carreira. Seu trabalho e orientar como
um senior revisando um curriculo real: claro, criterioso, honesto e orientado a impacto.

## CURRICULO/PERFIL ATUAL DO USUARIO
{profile}

## VAGA ALVO
Titulo: {job_title}
Empresa: {job_company}
Descricao:
{job_description}

## TAREFA
Otimize a orientacao do curriculo para esta vaga, mas sem criar um curriculo completo.
Voce pode sugerir headline, resumo profissional, ordem de foco, skills e bullets, desde
que tudo esteja baseado em informacoes existentes no curriculo/perfil do usuario.

Retorne SOMENTE JSON valido, sem markdown e sem texto extra:

{{
  "headline_sugerida": "<headline curta e profissional baseada no perfil real>",
  "resumo_profissional_sugerido": "<resumo profissional de 3 a 5 linhas, sem inventar experiencia>",
  "skills_prioritarias": ["<skill real do usuario que importa para a vaga>", "<outra skill>"],
  "experiencias_prioritarias": ["<experiencia/projeto real que deve aparecer primeiro>", "<outro foco>"],
  "bullets_sugeridos": ["<bullet reescrito com acao, tecnologia e impacto, baseado no perfil>", "<outro bullet>"],
  "reduzir_ou_remover": ["<item que pode receber menos destaque nesta candidatura>", "<outro item>"],
  "evidencias_ausentes": ["<requisito da vaga que nao aparece claramente no perfil>", "<outro requisito>"],
  "avisos_honestidade": ["<alerta para nao inventar ou verificar algo antes de incluir>", "<outro aviso>"],
  "proxima_acao": "<acao mais importante para ajustar o curriculo antes de aplicar>"
}}

## REGRAS IMPORTANTES
- Pense como senior: destaque impacto, escopo, tecnologias reais, senioridade evidenciada e aderencia aos requisitos principais.
- Priorize o que aumenta sinal para recrutador e ATS sem transformar o curriculo em texto generico.
- Nao invente experiencia, cargo, senioridade, empresa, certificacao, formacao, projeto ou tecnologia.
- Nao diga que o usuario tem uma skill se ela nao aparece no perfil/curriculo.
- Se algo seria bom para a vaga mas nao aparece no perfil, inclua em "evidencias_ausentes" ou "avisos_honestidade".
- Bullets sugeridos devem ser reescritas honestas de fatos existentes, nao fabricacoes.
- Nao crie uma versao final completa do curriculo.
- Nao inclua dados pessoais, contatos ou informacoes sensiveis.
- Escreva em portugues profissional e direto.
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


def calculate_local_resume_optimization(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
) -> ResumeOptimization:
    text = f"{job_title}\n{job_company}\n{job_description}".casefold()
    profile = profile_text.casefold()
    terms = [
        "java", "spring", "spring boot", "python", "node", "react", "sql",
        "postgres", "docker", "aws", "api", "rest", "backend", "frontend",
        "dados", "power bi", "excel", "git",
    ]
    matched = [term for term in terms if term in text and term in profile]
    missing = [term for term in terms if term in text and term not in profile]
    title = job_title or "vaga alvo"

    return ResumeOptimization(
        headline_sugerida=f"Profissional de tecnologia com foco alinhado a {title}.",
        resumo_profissional_sugerido=(
            "Resumo local gerado por palavras-chave. Priorize no topo do curriculo as experiencias "
            "e habilidades que aparecem tanto no seu perfil quanto na vaga."
        ),
        skills_prioritarias=matched[:8],
        experiencias_prioritarias=[
            "Experiencias e projetos mais proximos dos requisitos tecnicos da vaga.",
            "Resultados que demonstrem impacto, autonomia e entrega usando as tecnologias alinhadas.",
        ],
        bullets_sugeridos=[
            "Reescreva bullets relevantes usando o formato: acao executada, tecnologia utilizada e resultado obtido.",
            "Coloque primeiro os bullets que mencionam tecnologias e responsabilidades presentes na vaga.",
        ],
        reduzir_ou_remover=[
            "Itens muito distantes da area ou stack da vaga podem receber menos destaque nesta candidatura.",
        ],
        evidencias_ausentes=[f"A vaga menciona {term}, mas isso nao aparece claramente no perfil." for term in missing[:6]],
        avisos_honestidade=[
            "Inclua uma tecnologia ou responsabilidade somente se ela realmente fizer parte da sua experiencia.",
            "Se voce tiver experiencia com algum requisito ausente, deixe isso claro antes de se candidatar.",
        ],
        proxima_acao="Revisar resumo, skills e primeiros bullets para refletir os requisitos mais importantes da vaga.",
    )


def optimize_resume_for_job(
    profile_text: str,
    job_title: str,
    job_company: str,
    job_description: str,
    groq_api_key: str,
    model_name: str = "llama-3.3-70b-versatile",
    use_local_fallback: bool = True,
) -> Optional[ResumeOptimization]:
    try:
        from groq import Groq

        client = Groq(api_key=groq_api_key)
        prompt = _PROMPT.format(
            profile=profile_text[:14000],
            job_title=job_title or "Nao informado",
            job_company=job_company or "Nao informada",
            job_description=job_description[:6000],
        )

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.15,
            max_tokens=1400,
        )
        data = _extract_json(response.choices[0].message.content or "")

        return ResumeOptimization(
            headline_sugerida=str(data.get("headline_sugerida", "")).strip(),
            resumo_profissional_sugerido=str(data.get("resumo_profissional_sugerido", "")).strip(),
            skills_prioritarias=_as_list(data.get("skills_prioritarias")),
            experiencias_prioritarias=_as_list(data.get("experiencias_prioritarias")),
            bullets_sugeridos=_as_list(data.get("bullets_sugeridos")),
            reduzir_ou_remover=_as_list(data.get("reduzir_ou_remover")),
            evidencias_ausentes=_as_list(data.get("evidencias_ausentes")),
            avisos_honestidade=_as_list(data.get("avisos_honestidade")),
            proxima_acao=str(data.get("proxima_acao", "")).strip(),
        )
    except Exception as exc:
        print(f"[ResumeOptimizer] Erro: {exc}")
        if not use_local_fallback:
            return None
        return calculate_local_resume_optimization(profile_text, job_title, job_company, job_description)
