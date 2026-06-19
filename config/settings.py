"""Default settings plus user overrides stored outside the executable.

The desktop app writes the real user configuration to:
%APPDATA%/JobMatcher/config.json
"""

from core.user_config import load_user_config


DEFAULT_SEARCH_QUERIES = [
    "Java Developer Junior",
    "Java Backend Developer",
    "Desenvolvedor Java",
    "Programador Java",
    "Spring Boot Developer",
    "Java Spring Boot",
    "Desenvolvedor Spring Boot",
    "Backend Developer Junior",
    "Desenvolvedor Backend Junior",
    "Estagio Java",
    "Trainee Java",
    "Junior Software Engineer",
    "Java Remoto",
    "Java Backend Remoto",
    "Spring Boot Remoto",
]

DEFAULT_SEARCH_BASE_TERMS = [
    "Java",
    "Java Backend",
    "Spring Boot",
    "Backend",
    "Software Engineer",
    "Desenvolvedor Java",
    "Desenvolvedor Backend",
]

DEFAULT_SEARCH_SENIORITY_TERMS = [
    "Junior",
    "Jr",
    "Estagio",
    "Estagiario",
    "Trainee",
]

DEFAULT_SEARCH_WORK_MODES = [
    "Remoto",
    "Home Office",
]

DEFAULT_LOCATION_FILTERS = [
    "remoto",
    "remote",
    "home office",
]

ACTIVE_JOB_EXCLUDE_TERMS = [
    "vaga encerrada",
    "vaga expirada",
    "processo encerrado",
    "inscricoes encerradas",
    "inscrições encerradas",
    "nao aceita mais candidaturas",
    "não aceita mais candidaturas",
    "no longer accepting applications",
    "job expired",
    "job closed",
    "position closed",
    "applications closed",
    "not accepting applications",
    "this job is no longer available",
    "esta vaga nao esta mais disponivel",
    "esta vaga não está mais disponível",
]


def _as_list(value, default):
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    return list(default)


def reload_from_user_config():
    data = load_user_config()

    globals().update({
        "GROQ_API_KEY": str(data.get("groq_api_key", "")).strip(),
        "GROQ_MODEL": str(data.get("groq_model", "llama-3.3-70b-versatile")).strip() or "llama-3.3-70b-versatile",
        "SERPER_API_KEY": str(data.get("serper_api_key", "")).strip(),
        "EMAIL_REMETENTE": str(data.get("email_remetente", "")).strip(),
        "EMAIL_SENHA_APP": str(data.get("email_senha_app", "")).strip(),
        "EMAIL_DESTINATARIO": str(data.get("email_destinatario", "")).strip(),
        "MIN_SCORE": int(data.get("min_score", 90) or 90),
        "MAX_EMAIL_MATCHES_PER_SCAN": int(data.get("max_email_matches_per_scan", 10) or 10),
        "SEARCH_QUERIES": _as_list(data.get("search_queries"), DEFAULT_SEARCH_QUERIES),
        "SEARCH_BASE_TERMS": _as_list(data.get("search_base_terms"), DEFAULT_SEARCH_BASE_TERMS),
        "SEARCH_SENIORITY_TERMS": _as_list(data.get("search_seniority_terms"), DEFAULT_SEARCH_SENIORITY_TERMS),
        "SEARCH_WORK_MODES": _as_list(data.get("search_work_modes"), DEFAULT_SEARCH_WORK_MODES),
        "JOB_LOCATION_FILTERS": _as_list(data.get("job_location_filters"), DEFAULT_LOCATION_FILTERS),
        "TARGET_COMPANIES": _as_list(data.get("target_companies"), []),
        "MAX_SEARCH_QUERIES_PER_SOURCE": int(data.get("max_search_queries_per_source", 30) or 30),
        "MAX_JOBS_TO_ANALYZE_PER_SCAN": int(data.get("max_jobs_to_analyze_per_scan", 25) or 25),
        "SAVE_SCAN_REPORTS": bool(data.get("save_scan_reports", True)),
        "SERPER_DATE_RESTRICT": str(data.get("serper_date_restrict", "m1")).strip() or "m1",
        "VERIFY_ACTIVE_JOB_PAGES": bool(data.get("verify_active_job_pages", True)),
        "USE_DIRECT_SCRAPERS": bool(data.get("use_direct_scrapers", False)),
        "USE_LOCAL_MATCH_FALLBACK": bool(data.get("use_local_match_fallback", True)),
        "LOCATION": str(data.get("location", "Brasil")).strip() or "Brasil",
        "SCAN_INTERVAL_MINUTES": int(data.get("scan_interval_minutes", 60) or 60),
        "RESUME_PDF_PATH": str(data.get("resume_pdf_path", "")).strip() or None,
        "PROFILE_TEXT_PATH": str(data.get("profile_text_path", "")).strip() or None,
        "PROFILE_TEXT": str(data.get("profile_text", "")).strip(),
    })
    return data


reload_from_user_config()
