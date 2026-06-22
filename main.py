import sys
import time
import schedule
import logging
import re
import unicodedata
from datetime import datetime

sys.path.insert(0, ".")

from config.settings import (
    GROQ_API_KEY, GROQ_MODEL,
    EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_DESTINATARIO,
    MIN_SCORE, SEARCH_QUERIES, LOCATION,
    SCAN_INTERVAL_MINUTES, RESUME_PDF_PATH, PROFILE_TEXT
)
from config import settings
from scrapers.gupy_scraper import fetch_gupy_jobs
from scrapers.indeed_scraper import fetch_indeed_jobs
from scrapers.vagas_scraper import fetch_vagas_jobs
from scrapers.linkedin_scraper import fetch_linkedin_jobs
from scrapers.google_scraper import fetch_google_jobs
from core.job_analyzer import SingleJobAnalysis
from core.matcher import calculate_match, calculate_matches_batch
from core.resume_optimizer import optimize_resume_for_job
from core.ats_simulator import simulate_ats_for_job
from core.cover_letter import create_cover_letter_for_job
from core.market_trends import count_new_jobs, generate_market_report
from core.query_builder import build_search_queries
from core.resume_parser import build_profile
from core.user_config import is_configured, load_user_config
from core.cache import is_recent_job, mark_seen, get_stats
from core.report import save_scan_report
from notifier.email_notifier import send_job_digest, send_startup_email, JobAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("job_matcher.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

PROFILE = ""


def reload_profile():
    global PROFILE
    PROFILE = build_profile(
        getattr(settings, "PROFILE_TEXT", ""),
        getattr(settings, "RESUME_PDF_PATH", None),
        getattr(settings, "PROFILE_TEXT_PATH", None),
    )
    return PROFILE


def refresh_runtime_settings():
    global GROQ_API_KEY, GROQ_MODEL
    global EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_DESTINATARIO
    global MIN_SCORE, SEARCH_QUERIES, LOCATION, SCAN_INTERVAL_MINUTES, PROFILE

    settings.reload_from_user_config()
    GROQ_API_KEY = settings.GROQ_API_KEY
    GROQ_MODEL = settings.GROQ_MODEL
    EMAIL_REMETENTE = settings.EMAIL_REMETENTE
    EMAIL_SENHA_APP = settings.EMAIL_SENHA_APP
    EMAIL_DESTINATARIO = settings.EMAIL_DESTINATARIO
    MIN_SCORE = settings.MIN_SCORE
    SEARCH_QUERIES = settings.SEARCH_QUERIES
    LOCATION = settings.LOCATION
    SCAN_INTERVAL_MINUTES = settings.SCAN_INTERVAL_MINUTES
    try:
        reload_profile()
    except ValueError:
        PROFILE = ""


try:
    refresh_runtime_settings()
except ValueError:
    PROFILE = ""

def _normalize_key(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text

def _dedupe_jobs(jobs):
    unique = []
    seen = set()
    for job in jobs:
        key = (
            _normalize_key(job.title),
            _normalize_key(job.company),
            _normalize_key(job.source),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique

def _dedupe_alerts(alerts):
    unique = []
    seen = set()
    for alert in alerts:
        key = (
            _normalize_key(alert.title),
            _normalize_key(alert.company),
            _normalize_key(alert.source),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(alert)
    return unique

def get_search_queries():
    return build_search_queries(
        base_terms=getattr(settings, "SEARCH_BASE_TERMS", []),
        seniority_terms=getattr(settings, "SEARCH_SENIORITY_TERMS", []),
        work_modes=getattr(settings, "SEARCH_WORK_MODES", []),
        companies=getattr(settings, "TARGET_COMPANIES", []),
        manual_queries=SEARCH_QUERIES,
        max_queries=getattr(settings, "MAX_SEARCH_QUERIES_PER_SOURCE", 50),
    )

def analyze_manual_job(job_title, job_company, job_description):
    refresh_runtime_settings()
    if not GROQ_API_KEY:
        raise ValueError("Configure a API da IA antes de analisar uma vaga.")
    if not PROFILE:
        reload_profile()
    if not PROFILE:
        raise ValueError("Configure um curriculo PDF, TXT de perfil ou texto de perfil antes de analisar.")
    if not job_description or len(job_description.strip()) < 80:
        raise ValueError("Cole uma descricao de vaga mais completa antes de analisar.")

    result = calculate_match(
        profile_text=PROFILE,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        use_local_fallback=getattr(settings, "USE_LOCAL_MATCH_FALLBACK", True),
    )
    if result is None:
        return None

    return SingleJobAnalysis(
        score=result.score,
        veredito=result.resumo,
        pontos_fortes=result.pontos_fortes,
        pontos_fracos=result.gaps,
        melhorias_curriculo=result.curriculo_ajustes,
        itens_menos_relevantes=[
            "Informacoes que nao reforcam os requisitos principais desta vaga podem receber menos destaque.",
            "Priorize no topo do curriculo os pontos listados em foco e pontos fortes.",
        ],
        prioridade_ajuste="alta" if result.score < 70 else "media" if result.score < 85 else "baixa",
        proxima_acao=(
            "Ajustar o resumo e os primeiros bullets do curriculo usando os pontos fortes e ajustes honestos acima."
        ),
    )

def optimize_manual_resume(job_title, job_company, job_description):
    refresh_runtime_settings()
    if not GROQ_API_KEY:
        raise ValueError("Configure a API da IA antes de otimizar o curriculo.")
    if not PROFILE:
        reload_profile()
    if not PROFILE:
        raise ValueError("Configure um curriculo PDF, TXT de perfil ou texto de perfil antes de otimizar.")
    if not job_description or len(job_description.strip()) < 80:
        raise ValueError("Cole uma descricao de vaga mais completa antes de otimizar.")

    return optimize_resume_for_job(
        profile_text=PROFILE,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        use_local_fallback=getattr(settings, "USE_LOCAL_MATCH_FALLBACK", True),
    )

def simulate_manual_ats(job_title, job_company, job_description):
    refresh_runtime_settings()
    if not GROQ_API_KEY:
        raise ValueError("Configure a API da IA antes de simular ATS.")
    resume_path = getattr(settings, "RESUME_PDF_PATH", None)
    if not resume_path:
        raise ValueError("Configure um curriculo PDF antes de simular ATS.")
    if not job_description or len(job_description.strip()) < 80:
        raise ValueError("Cole uma descricao de vaga mais completa antes de simular ATS.")

    return simulate_ats_for_job(
        resume_pdf_path=resume_path,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        open_browser=True,
    )

def generate_manual_cover_letter(job_title, job_company, job_description):
    refresh_runtime_settings()
    if not GROQ_API_KEY:
        raise ValueError("Configure a API da IA antes de gerar carta.")
    if not PROFILE:
        reload_profile()
    if not PROFILE:
        raise ValueError("Configure um perfil TXT, texto de perfil ou curriculo antes de gerar carta.")
    resume_path = getattr(settings, "RESUME_PDF_PATH", None)
    if not resume_path:
        raise ValueError("Configure um curriculo PDF antes de gerar carta.")
    if not job_description or len(job_description.strip()) < 80:
        raise ValueError("Cole uma descricao de vaga mais completa antes de gerar carta.")

    return create_cover_letter_for_job(
        profile_text=PROFILE,
        resume_pdf_path=resume_path,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        open_browser=True,
    )

def count_new_market_trend_jobs():
    return count_new_jobs()

def generate_manual_market_trends(progress=None):
    refresh_runtime_settings()
    if not GROQ_API_KEY:
        raise ValueError("Configure a API da IA antes de gerar tendencias.")
    if not PROFILE:
        reload_profile()
    return generate_market_report(
        profile_text=PROFILE,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        progress=progress,
        open_browser=True,
    )

def run_scan(max_jobs_override=None, should_stop=None):
    refresh_runtime_settings()
    if not is_configured(load_user_config()):
        log.error("Configuracao incompleta. Abra Configurar e informe IA, Serper, e-mail e perfil/curriculo.")
        return

    log.info("=" * 60)
    log.info(f"Varredura — {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    all_jobs = []
    search_queries = get_search_queries()
    max_jobs = max_jobs_override
    if max_jobs is None:
        max_jobs = getattr(settings, "MAX_JOBS_TO_ANALYZE_PER_SCAN", 25)
    query_limit = len(search_queries)
    if max_jobs:
        query_limit = min(len(search_queries), max(3, int(max_jobs)))
    limited_search_queries = search_queries[:query_limit]
    log.info(f"Queries ativas: {len(search_queries)} | Usadas nesta varredura: {len(limited_search_queries)}")

    fontes = []
    serper_api_key = getattr(settings, "SERPER_API_KEY", "")
    if serper_api_key:
        fontes.append((
            "Google/Serper",
            lambda: fetch_google_jobs(
                limited_search_queries,
                LOCATION,
                serper_api_key,
                location_filters=getattr(settings, "JOB_LOCATION_FILTERS", []),
                exclude_terms=getattr(settings, "ACTIVE_JOB_EXCLUDE_TERMS", []),
                date_restrict=getattr(settings, "SERPER_DATE_RESTRICT", "m1"),
                verify_active_pages=getattr(settings, "VERIFY_ACTIVE_JOB_PAGES", True),
                max_jobs=max_jobs,
                skip_job=is_recent_job,
            )
        ))
    else:
        log.error("SERPER_API_KEY nao configurada. O Serper e a fonte principal de busca.")

    if getattr(settings, "USE_DIRECT_SCRAPERS", False):
        fontes.extend([
            ("Gupy",          lambda: fetch_gupy_jobs(limited_search_queries, LOCATION)),
            ("Indeed",        lambda: fetch_indeed_jobs(limited_search_queries, LOCATION)),
            ("Vagas.com.br",  lambda: fetch_vagas_jobs(limited_search_queries, LOCATION)),
            ("LinkedIn",      lambda: fetch_linkedin_jobs(limited_search_queries, LOCATION)),
        ])

    if not fontes:
        log.error("Nenhuma fonte ativa. Configure SERPER_API_KEY ou habilite USE_DIRECT_SCRAPERS.")
        return

    for nome, fetch in fontes:
        if should_stop and should_stop():
            log.info("Varredura interrompida antes de consultar novas fontes.")
            return
        if max_jobs and len(all_jobs) >= max_jobs:
            log.info(f"Coleta limitada a {max_jobs} vaga(s) candidata(s) nesta varredura.")
            break

        try:
            vagas = fetch()
            log.info(f"{nome}: {len(vagas)} vagas")
            all_jobs.extend(vagas)
        except Exception as e:
            log.error(f"{nome}: erro — {e}")

    total_before_dedupe = len(all_jobs)
    all_jobs = _dedupe_jobs(all_jobs)
    log.info(f"Total coletado: {total_before_dedupe} | Unicas: {len(all_jobs)}")

    novas = [j for j in all_jobs if not is_recent_job(j)]
    blocked_recent = len(all_jobs) - len(novas)
    log.info(f"Novas para analisar: {len(novas)} | Bloqueadas por cache 30d: {blocked_recent}")
    if max_jobs and len(novas) > max_jobs:
        log.info(f"Limitando analise a {max_jobs} vagas nesta varredura")
        novas = novas[:max_jobs]

    if not novas:
        log.info("Nenhuma vaga nova. Aguardando próxima varredura.")
        return

    notificadas = 0
    analyzed_records = []
    matched_alerts = []
    jobs_to_analyze = []
    for job in novas:
        if should_stop and should_stop():
            log.info("Varredura interrompida antes de analisar a proxima vaga.")
            break

        if not job.description or len(job.description) < 50:
            log.warning("  → Descrição insuficiente, pulando")
            mark_seen(job.id, score=0, job=job)
            continue
        jobs_to_analyze.append(job)

    if not jobs_to_analyze:
        log.info("Nenhuma vaga com descricao suficiente para analise.")
        return

    if should_stop and should_stop():
        log.info("Varredura interrompida antes da analise de compatibilidade.")
        return

    log.info(f"Analisando compatibilidade de {len(jobs_to_analyze)} vaga(s) em uma unica chamada de IA.")
    batch_results = calculate_matches_batch(
        profile_text=PROFILE,
        jobs=jobs_to_analyze,
        groq_api_key=GROQ_API_KEY,
        model_name=GROQ_MODEL,
        use_local_fallback=getattr(settings, "USE_LOCAL_MATCH_FALLBACK", True),
    )

    for job in jobs_to_analyze:
        if should_stop and should_stop():
            log.info("Varredura interrompida ao processar resultados da analise.")
            break

        log.info(f"Resultado: [{job.source}] {job.title} @ {job.company}")
        result = batch_results.get(str(job.id))

        if result is None:
            log.error("Falha no match em lote, tentando analise individual.")
            result = calculate_match(
                profile_text=PROFILE,
                job_title=job.title,
                job_company=job.company,
                job_description=job.description,
                groq_api_key=GROQ_API_KEY,
                model_name=GROQ_MODEL,
                use_local_fallback=getattr(settings, "USE_LOCAL_MATCH_FALLBACK", True),
            )

        if result is None:
            log.error("  → Falha no match, pulando")
            continue

        mark_seen(job.id, score=result.score, job=job)
        analyzed_records.append({
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "source": job.source,
            "score": result.score,
            "pontos_fortes": result.pontos_fortes,
            "gaps": result.gaps,
            "resumo": result.resumo,
            "curriculo_foco": result.curriculo_foco,
            "curriculo_ajustes": result.curriculo_ajustes,
            "curriculo_headline": result.curriculo_headline,
            "description": job.description,
        })
        if result.score >= MIN_SCORE:
            matched_alerts.append(JobAlert(
                title=job.title, company=job.company,
                location=job.location, url=job.url, source=job.source,
                score=result.score, pontos_fortes=result.pontos_fortes,
                gaps=result.gaps, resumo=result.resumo,
                curriculo_foco=result.curriculo_foco,
                curriculo_ajustes=result.curriculo_ajustes,
                curriculo_headline=result.curriculo_headline,
            ))
        log.info(f"  → {result.score}% | {result.resumo}")

        if False and result.score >= MIN_SCORE:
            log.info(f"  → 🎯 Match! Enviando e-mail...")
            alert = JobAlert(
                title=job.title, company=job.company,
                location=job.location, url=job.url, source=job.source,
                score=result.score, pontos_fortes=result.pontos_fortes,
                gaps=result.gaps, resumo=result.resumo,
                curriculo_foco=result.curriculo_foco,
                curriculo_ajustes=result.curriculo_ajustes,
                curriculo_headline=result.curriculo_headline,
            )
            if send_job_alert(alert, EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_DESTINATARIO):
                notificadas += 1
                log.info("  → E-mail enviado!")
            else:
                log.error("  → Falha no envio")

    report_json = None
    report_md = None
    if getattr(settings, "SAVE_SCAN_REPORTS", True):
        report_json, report_md = save_scan_report(all_jobs, analyzed_records, MIN_SCORE)
        log.info(f"Relatorio salvo: {report_md}")

    matched_alerts = _dedupe_alerts(matched_alerts)
    matched_alerts.sort(key=lambda alert: alert.score, reverse=True)
    max_email = getattr(settings, "MAX_EMAIL_MATCHES_PER_SCAN", 10)
    matched_alerts = matched_alerts[:max_email]

    if matched_alerts:
        report_path = str(report_md or report_json or "")
        log.info(f"Enviando resumo com {len(matched_alerts)} match(es)")
        if send_job_digest(matched_alerts, report_path, EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_DESTINATARIO, MIN_SCORE):
            notificadas = len(matched_alerts)
            log.info("Resumo enviado!")
        else:
            log.error("Falha no envio do resumo")
    else:
        log.info(f"Nenhuma vaga atingiu {MIN_SCORE}% nesta varredura. Sem e-mail.")

    log.info(f"Concluida | Matches no e-mail: {notificadas} | {get_stats()}")

def main():
    log.info("🚀 Job Matcher iniciando...")

    refresh_runtime_settings()
    erros = []
    if not GROQ_API_KEY: erros.append("GROQ_API_KEY")
    if not getattr(settings, "SERPER_API_KEY", ""): erros.append("SERPER_API_KEY")
    if not EMAIL_REMETENTE: erros.append("EMAIL_REMETENTE")
    if not EMAIL_SENHA_APP: erros.append("EMAIL_SENHA_APP")
    if not EMAIL_DESTINATARIO: erros.append("EMAIL_DESTINATARIO")
    if not PROFILE: erros.append("PERFIL/CURRICULO")
    if erros:
        log.error(f"Configure no app desktop ou em %APPDATA%/JobMatcher/config.json: {', '.join(erros)}")
        sys.exit(1)

    log.info(f"Score mínimo: {MIN_SCORE}% | Intervalo: {SCAN_INTERVAL_MINUTES}min")
    send_startup_email(EMAIL_REMETENTE, EMAIL_SENHA_APP, EMAIL_DESTINATARIO, get_search_queries(), MIN_SCORE)

    run_scan()

    schedule.every(SCAN_INTERVAL_MINUTES).minutes.do(run_scan)
    log.info(f"Próxima varredura em {SCAN_INTERVAL_MINUTES} min. Ctrl+C para parar.")

    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    main()
