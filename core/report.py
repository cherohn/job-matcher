import json
import re
import unicodedata
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from core.html_reporter import generate_job_analysis_report, generate_resume_optimization_report, generate_scan_report


REPORT_DIR = Path(__file__).parent.parent / "reports"


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "vaga"


def _md_list(items: list[str]) -> list[str]:
    if not items:
        return ["- Nenhum ponto especifico identificado."]
    return [f"- {item}" for item in items]


def save_scan_report(
    collected_jobs: List[Any],
    analyzed_jobs: List[Dict[str, Any]],
    min_score: int,
) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_DIR / f"scan-{stamp}.json"
    md_path = REPORT_DIR / f"scan-{stamp}.md"

    analyzed_sorted = sorted(analyzed_jobs, key=lambda item: item.get("score", 0), reverse=True)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "min_score": min_score,
        "collected_count": len(collected_jobs),
        "analyzed_count": len(analyzed_jobs),
        "matches_count": sum(1 for item in analyzed_jobs if item.get("score", 0) >= min_score),
        "collected_jobs": _plain(collected_jobs),
        "analyzed_jobs": analyzed_sorted,
    }

    lines = [
        "# Job Matcher Scan",
        "",
        f"- Coletadas: {len(collected_jobs)}",
        f"- Analisadas: {len(analyzed_jobs)}",
        f"- Corte de e-mail: {min_score}%",
        f"- Matches: {payload['matches_count']}",
        "",
        "## Vagas Analisadas",
        "",
    ]
    for item in analyzed_sorted:
        lines.extend([
            f"### {item.get('score', 0)}% - {item.get('title', 'Sem titulo')}",
            "",
            f"- Empresa: {item.get('company', 'Nao informado')}",
            f"- Fonte: {item.get('source', 'Nao informado')}",
            f"- URL: {item.get('url', '')}",
            f"- Resumo: {item.get('resumo', '')}",
            f"- Pontos fortes: {'; '.join(item.get('pontos_fortes', []))}",
            f"- Gaps: {'; '.join(item.get('gaps', [])) if item.get('gaps') else 'Nenhum'}",
            f"- Headline sugerida: {item.get('curriculo_headline', '') or 'Nao gerada'}",
            f"- Foco do curriculo: {'; '.join(item.get('curriculo_foco', [])) if item.get('curriculo_foco') else 'Nao gerado'}",
            f"- Ajustes no curriculo: {'; '.join(item.get('curriculo_ajustes', [])) if item.get('curriculo_ajustes') else 'Nao gerado'}",
            "",
        ])

    md_path.write_text("\n".join(lines), encoding="utf-8")
    html_path = generate_scan_report(
        payload["collected_jobs"],
        analyzed_sorted,
        min_score,
        filename_base=json_path.stem,
    )
    try:
        payload["html_report"] = str(html_path.relative_to(REPORT_DIR))
    except ValueError:
        payload["html_report"] = str(html_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, md_path


def save_manual_analysis_report(
    job_title: str,
    job_company: str,
    job_description: str,
    analysis: Any,
) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    name = _slug(f"{job_company}-{job_title}")
    json_path = REPORT_DIR / f"manual-{stamp}-{name}.json"
    md_path = REPORT_DIR / f"manual-{stamp}-{name}.md"

    analysis_data = _plain(analysis)
    payload = {
        "created_at": now.isoformat(timespec="seconds"),
        "type": "manual_job_analysis",
        "job": {
            "title": job_title or "Nao informado",
            "company": job_company or "Nao informada",
            "description": job_description,
        },
        "analysis": analysis_data,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Analise Manual de Vaga",
        "",
        f"- Criada em: {now.strftime('%d/%m/%Y %H:%M')}",
        f"- Vaga: {job_title or 'Nao informado'}",
        f"- Empresa: {job_company or 'Nao informada'}",
        f"- Score: {analysis_data.get('score', 0)}%",
        f"- Prioridade de ajuste: {analysis_data.get('prioridade_ajuste', 'media')}",
        "",
        "## Veredito",
        "",
        analysis_data.get("veredito") or "Nao informado.",
        "",
        "## Pontos Fortes",
        "",
        *_md_list(analysis_data.get("pontos_fortes", [])),
        "",
        "## Pontos Fracos ou Gaps",
        "",
        *_md_list(analysis_data.get("pontos_fracos", [])),
        "",
        "## Melhorias Recomendadas no Curriculo",
        "",
        *_md_list(analysis_data.get("melhorias_curriculo", [])),
        "",
        "## Itens que Podem Perder Destaque",
        "",
        *_md_list(analysis_data.get("itens_menos_relevantes", [])),
        "",
        "## Proxima Acao",
        "",
        analysis_data.get("proxima_acao") or "Nao informada.",
        "",
        "## Descricao da Vaga",
        "",
        job_description,
        "",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    html_path = generate_job_analysis_report(
        job_title,
        job_company,
        job_description,
        analysis_data,
        filename_base=json_path.stem,
    )
    try:
        payload["html_report"] = str(html_path.relative_to(REPORT_DIR))
    except ValueError:
        payload["html_report"] = str(html_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, md_path


def save_resume_optimization_report(
    job_title: str,
    job_company: str,
    job_description: str,
    optimization: Any,
) -> Tuple[Path, Path]:
    REPORT_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S")
    name = _slug(f"{job_company}-{job_title}")
    json_path = REPORT_DIR / f"optimized-{stamp}-{name}.json"
    md_path = REPORT_DIR / f"optimized-{stamp}-{name}.md"

    optimization_data = _plain(optimization)
    payload = {
        "created_at": now.isoformat(timespec="seconds"),
        "type": "resume_optimization",
        "job": {
            "title": job_title or "Nao informado",
            "company": job_company or "Nao informada",
            "description": job_description,
        },
        "optimization": optimization_data,
    }
    lines = [
        "# Otimizacao de Curriculo",
        "",
        f"- Criada em: {now.strftime('%d/%m/%Y %H:%M')}",
        f"- Vaga: {job_title or 'Nao informado'}",
        f"- Empresa: {job_company or 'Nao informada'}",
        "",
        "## Headline Sugerida",
        "",
        optimization_data.get("headline_sugerida") or "Nao gerada.",
        "",
        "## Resumo Profissional Sugerido",
        "",
        optimization_data.get("resumo_profissional_sugerido") or "Nao gerado.",
        "",
        "## Skills Prioritarias",
        "",
        *_md_list(optimization_data.get("skills_prioritarias", [])),
        "",
        "## Experiencias ou Projetos para Priorizar",
        "",
        *_md_list(optimization_data.get("experiencias_prioritarias", [])),
        "",
        "## Bullets Sugeridos",
        "",
        *_md_list(optimization_data.get("bullets_sugeridos", [])),
        "",
        "## Reduzir ou Remover Destaque",
        "",
        *_md_list(optimization_data.get("reduzir_ou_remover", [])),
        "",
        "## Evidencias Ausentes",
        "",
        *_md_list(optimization_data.get("evidencias_ausentes", [])),
        "",
        "## Avisos de Honestidade",
        "",
        *_md_list(optimization_data.get("avisos_honestidade", [])),
        "",
        "## Proxima Acao",
        "",
        optimization_data.get("proxima_acao") or "Nao informada.",
        "",
        "## Descricao da Vaga",
        "",
        job_description,
        "",
    ]

    md_path.write_text("\n".join(lines), encoding="utf-8")
    html_path = generate_resume_optimization_report(
        job_title,
        job_company,
        job_description,
        optimization_data,
        filename_base=json_path.stem,
    )
    try:
        payload["html_report"] = str(html_path.relative_to(REPORT_DIR))
    except ValueError:
        payload["html_report"] = str(html_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path, md_path


def _relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(REPORT_DIR))
    except ValueError:
        return str(path)


def _resolve_html_path(payload: Dict[str, Any], json_path: Path, report_type: str) -> Path | None:
    html_report = payload.get("html_report")
    if html_report:
        html_path = Path(html_report)
        if not html_path.is_absolute():
            html_path = REPORT_DIR / html_path
        if html_path.exists():
            return html_path

    try:
        if report_type == "manual_job_analysis":
            job = payload.get("job", {})
            html_path = generate_job_analysis_report(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                payload.get("analysis", {}),
                filename_base=json_path.stem,
            )
        elif report_type == "resume_optimization":
            job = payload.get("job", {})
            html_path = generate_resume_optimization_report(
                job.get("title", ""),
                job.get("company", ""),
                job.get("description", ""),
                payload.get("optimization", {}),
                filename_base=json_path.stem,
            )
        elif report_type == "ats_simulation":
            return None
        elif report_type == "cover_letter":
            return None
        else:
            html_path = generate_scan_report(
                payload.get("collected_jobs", []),
                payload.get("analyzed_jobs", []),
                int(payload.get("min_score", 0) or 0),
                filename_base=json_path.stem,
            )
    except Exception:
        return None

    payload["html_report"] = _relative_or_absolute(html_path)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return html_path


def list_report_summaries(limit: int = 30) -> List[Dict[str, Any]]:
    REPORT_DIR.mkdir(exist_ok=True)
    reports = []
    for json_path in sorted(REPORT_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        report_type = payload.get("type") or "scan"
        created_at = payload.get("created_at") or ""
        md_path = json_path.with_suffix(".md")
        html_path = _resolve_html_path(payload, json_path, report_type)
        title = "Varredura de vagas"
        company = ""
        score = None
        detail = ""

        if report_type == "manual_job_analysis":
            job = payload.get("job", {})
            analysis = payload.get("analysis", {})
            title = job.get("title") or "Vaga analisada"
            company = job.get("company") or ""
            score = analysis.get("score")
            detail = "Analise manual"
        elif report_type == "resume_optimization":
            job = payload.get("job", {})
            title = job.get("title") or "Curriculo otimizado"
            company = job.get("company") or ""
            detail = "Otimizacao de curriculo"
        elif report_type == "ats_simulation":
            job = payload.get("job", {})
            analysis = payload.get("analysis", {})
            title = job.get("title") or "Simulacao ATS"
            company = job.get("company") or ""
            score = analysis.get("coverage_score")
            detail = "Simulacao ATS"
        elif report_type == "cover_letter":
            job = payload.get("job", {})
            letter = payload.get("letter", {})
            title = job.get("title") or "Carta de apresentacao"
            company = job.get("company") or ""
            detail = f"Carta | {letter.get('idioma', 'idioma nao informado')} | {letter.get('word_count', 0)} palavras"
        else:
            matches = payload.get("matches_count", 0)
            analyzed = payload.get("analyzed_count", 0)
            detail = f"Varredura: {matches} match(es), {analyzed} analisada(s)"

        reports.append({
            "type": report_type,
            "created_at": created_at,
            "title": title,
            "company": company,
            "score": score,
            "detail": detail,
            "json_path": json_path,
            "md_path": md_path if md_path.exists() else json_path,
            "open_path": html_path if html_path and html_path.exists() else md_path if md_path.exists() else json_path,
        })
        if len(reports) >= limit:
            break
    return reports
