import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from core.html_reporter import REPORTS_ROOT, generate_market_trends_report, slugify
from core.report import REPORT_DIR
from core.user_config import get_app_data_dir


TRENDS_FILE = get_app_data_dir() / "market_trends.json"
BATCH_SIZE = 10

_PROMPT = """
Voce extrai metadados objetivos de vagas de tecnologia.

Para cada vaga, retorne tecnologias/ferramentas/metodologias/certificacoes mencionadas,
senioridade, modalidade e empresa.

Retorne SOMENTE JSON valido, sem markdown e sem texto extra:

{{
  "jobs": [
    {{
      "id": "<id recebido>",
      "technologies": ["Java", "Spring Boot"],
      "seniority": "junior|pleno|senior|nao informado",
      "work_mode": "remoto|hibrido|presencial|nao informado",
      "company": "<empresa>"
    }}
  ]
}}

## VAGAS
{jobs}
"""


def _load_trends() -> Dict[str, Any]:
    if not TRENDS_FILE.exists():
        return {"analyzed_ids": [], "records": []}
    try:
        data = json.loads(TRENDS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"analyzed_ids": [], "records": []}
        data.setdefault("analyzed_ids", [])
        data.setdefault("records", [])
        return data
    except Exception:
        return {"analyzed_ids": [], "records": []}


def _save_trends(data: Dict[str, Any]) -> None:
    TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = TRENDS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(TRENDS_FILE)


def _chunks(values: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _normalize_id(job: Dict[str, Any]) -> str:
    raw = job.get("id") or "|".join([
        str(job.get("title", "")),
        str(job.get("company", "")),
        str(job.get("url", "")),
    ])
    return str(raw)


def collect_jobs_from_scan_reports() -> List[Dict[str, Any]]:
    jobs = []
    seen = set()
    for path in sorted(REPORT_DIR.glob("scan-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        created_at = payload.get("created_at", "")
        for item in payload.get("analyzed_jobs", []):
            if not isinstance(item, dict):
                continue
            job_id = _normalize_id(item)
            if job_id in seen:
                continue
            seen.add(job_id)
            copy = dict(item)
            copy["id"] = job_id
            copy["scan_created_at"] = created_at
            jobs.append(copy)
    return jobs


def count_new_jobs() -> int:
    trends = _load_trends()
    analyzed = set(trends.get("analyzed_ids", []))
    return sum(1 for job in collect_jobs_from_scan_reports() if _normalize_id(job) not in analyzed)


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"JSON invalido na resposta de tendencias: {text[:300]}")


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _analyze_batch(batch: List[Dict[str, Any]], groq_api_key: str, model_name: str) -> List[Dict[str, Any]]:
    from groq import Groq

    payload = []
    for job in batch:
        payload.append({
            "id": job.get("id"),
            "title": job.get("title"),
            "company": job.get("company"),
            "description": str(job.get("description", ""))[:2500],
        })
    client = Groq(api_key=groq_api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "Return only valid JSON. No markdown, no explanation."},
            {"role": "user", "content": _PROMPT.format(jobs=json.dumps(payload, ensure_ascii=False))},
        ],
        temperature=0.1,
        max_tokens=1800,
    )
    data = _extract_json(response.choices[0].message.content or "")
    records = data.get("jobs", [])
    return records if isinstance(records, list) else []


def _clean_record(record: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    seniority = str(record.get("seniority", "nao informado")).strip().casefold()
    if seniority not in {"junior", "pleno", "senior", "nao informado"}:
        seniority = "nao informado"
    work_mode = str(record.get("work_mode", "nao informado")).strip().casefold()
    if work_mode not in {"remoto", "hibrido", "presencial", "nao informado"}:
        work_mode = "nao informado"
    return {
        "id": str(record.get("id") or fallback.get("id")),
        "title": fallback.get("title", ""),
        "company": str(record.get("company") or fallback.get("company") or "Nao informada").strip(),
        "technologies": _as_list(record.get("technologies")),
        "seniority": seniority,
        "work_mode": work_mode,
        "source": fallback.get("source", ""),
        "scan_created_at": fallback.get("scan_created_at", ""),
        "analyzed_at": datetime.now().isoformat(timespec="seconds"),
    }


def _percent(counter: Counter, total: int, limit: int) -> list[dict[str, Any]]:
    if not total:
        return []
    return [
        {"name": name, "count": count, "percent": round((count / total) * 100)}
        for name, count in counter.most_common(limit)
    ]


def aggregate_trends(profile_text: str = "") -> Dict[str, Any]:
    trends = _load_trends()
    records = [item for item in trends.get("records", []) if isinstance(item, dict)]
    total = len(records)
    tech_counter = Counter()
    seniority_counter = Counter()
    mode_counter = Counter()
    company_counter = Counter()
    for record in records:
        for tech in set(_as_list(record.get("technologies"))):
            tech_counter[tech] += 1
        seniority_counter[record.get("seniority", "nao informado")] += 1
        mode_counter[record.get("work_mode", "nao informado")] += 1
        company_counter[record.get("company") or "Nao informada"] += 1

    profile_norm = (profile_text or "").casefold()
    gaps = []
    for tech, count in tech_counter.most_common(10):
        if total and count / total > 0.5 and tech.casefold() not in profile_norm:
            gaps.append(f"{tech} aparece em {round((count / total) * 100)}% das vagas e nao aparece no perfil.")

    dates = [str(item.get("scan_created_at", ""))[:10] for item in records if item.get("scan_created_at")]
    period = "Nao informado"
    if dates:
        period = f"{min(dates)} a {max(dates)}"

    return {
        "title": "Tendencias de mercado",
        "total_jobs": total,
        "processed_success": total,
        "period": period,
        "technologies": _percent(tech_counter, total, 15),
        "skill_gaps": gaps,
        "seniority": _percent(seniority_counter, total, 4),
        "work_modes": _percent(mode_counter, total, 4),
        "companies": _percent(company_counter, total, 8),
    }


def generate_market_report(
    profile_text: str,
    groq_api_key: str,
    model_name: str,
    progress: Optional[Callable[[str], None]] = None,
    open_browser: bool = True,
) -> tuple[Path, Dict[str, Any]]:
    trends = _load_trends()
    analyzed = set(trends.get("analyzed_ids", []))
    records = list(trends.get("records", []))
    jobs = [job for job in collect_jobs_from_scan_reports() if _normalize_id(job) not in analyzed]
    attempted = len(jobs)
    success = 0

    for batch_index, batch in enumerate(_chunks(jobs, BATCH_SIZE), start=1):
        if progress:
            progress(f"Processando lote {batch_index} com {len(batch)} vaga(s)...")
        try:
            response_records = _analyze_batch(batch, groq_api_key, model_name)
            by_id = {str(item.get("id")): item for item in response_records if isinstance(item, dict)}
            for job in batch:
                cleaned = _clean_record(by_id.get(str(job.get("id")), {}), job)
                records.append(cleaned)
                analyzed.add(str(job.get("id")))
                success += 1
        except Exception as exc:
            if progress:
                progress(f"Lote {batch_index} falhou: {exc}")
            continue

    trends["analyzed_ids"] = sorted(analyzed)
    trends["records"] = records
    trends["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _save_trends(trends)

    aggregated = aggregate_trends(profile_text)
    aggregated["attempted"] = attempted
    aggregated["new_processed_success"] = success
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    html_path = generate_market_trends_report(aggregated, slugify(f"tendencias-{stamp}"), open_browser=open_browser)
    try:
        html_report = str(html_path.relative_to(REPORTS_ROOT))
    except ValueError:
        html_report = str(html_path)
    (REPORTS_ROOT / f"tendencias-{stamp}.json").write_text(
        json.dumps({
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "type": "market_trends",
            "summary": aggregated,
            "html_report": html_report,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return html_path, aggregated
