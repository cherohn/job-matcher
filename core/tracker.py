import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.user_config import get_app_data_dir


APPLICATIONS_FILE = get_app_data_dir() / "applications.json"
FOLLOW_UP_DAYS = 7

STATUS_LABELS = {
    "enviado": "Enviado",
    "triagem": "Triagem / RH",
    "entrevista": "Entrevista",
    "encerrado": "Encerrado",
}
STATUS_ORDER = ["enviado", "triagem", "entrevista", "encerrado"]
RESPONSE_STATUSES = {"triagem", "entrevista", "encerrado"}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today_iso() -> str:
    return date.today().isoformat()


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _load() -> Dict[str, Any]:
    if not APPLICATIONS_FILE.exists():
        return {}
    try:
        data = json.loads(APPLICATIONS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: Dict[str, Any]) -> None:
    APPLICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = APPLICATIONS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(APPLICATIONS_FILE)


def load_applications() -> Dict[str, Any]:
    return _load()


def _make_application_id(title: str, company: str, url: str) -> str:
    raw = "|".join([title or "", company or "", url or ""]).casefold().encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def register_application(
    title: str,
    company: str,
    url: str = "",
    score_fit: Optional[int] = None,
    source: str = "",
) -> tuple[str, bool]:
    data = _load()
    app_id = _make_application_id(title, company, url)
    if app_id in data:
        return app_id, False

    data[app_id] = {
        "id": app_id,
        "empresa": company or "Nao informada",
        "cargo": title or "Vaga sem titulo",
        "url": url or "",
        "source": source or "",
        "score_fit": score_fit,
        "data_envio": _today_iso(),
        "status": "enviado",
        "contato": "",
        "notas": "",
        "proxima_acao": "",
        "first_response_at": "",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _save(data)
    return app_id, True


def update_application(app_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    data = _load()
    if app_id not in data:
        raise KeyError("Candidatura nao encontrada.")

    current = data[app_id]
    old_status = current.get("status", "enviado")
    new_status = str(updates.get("status", old_status) or old_status)
    if new_status not in STATUS_LABELS:
        new_status = old_status if old_status in STATUS_LABELS else "enviado"

    current.update({
        key: value
        for key, value in updates.items()
        if key in {"status", "contato", "notas", "proxima_acao"}
    })
    current["status"] = new_status
    if old_status == "enviado" and new_status in RESPONSE_STATUSES and not current.get("first_response_at"):
        current["first_response_at"] = _today_iso()
    current["updated_at"] = _now_iso()
    _save(data)
    return current


def get_follow_up_alerts(days: int = FOLLOW_UP_DAYS) -> list[Dict[str, Any]]:
    today = date.today()
    alerts = []
    for item in _load().values():
        status = item.get("status", "enviado")
        if status not in {"enviado", "triagem"}:
            continue
        sent_at = _parse_date(item.get("data_envio", ""))
        if sent_at and (today - sent_at).days > days:
            copy = dict(item)
            copy["dias_desde_envio"] = (today - sent_at).days
            alerts.append(copy)
    return alerts


def calculate_metrics(applications: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = applications if applications is not None else _load()
    items = list(data.values())
    total = len(items)
    responded = [item for item in items if item.get("status") in RESPONSE_STATUSES or item.get("first_response_at")]
    interviews = [item for item in items if item.get("status") in {"entrevista", "encerrado"}]
    response_days = []
    for item in responded:
        sent_at = _parse_date(item.get("data_envio", ""))
        first_response = _parse_date(item.get("first_response_at", ""))
        if sent_at and first_response and first_response >= sent_at:
            response_days.append((first_response - sent_at).days)

    return {
        "total": total,
        "respondidas": len(responded),
        "taxa_entrevista": round((len(interviews) / total) * 100, 1) if total else 0,
        "tempo_medio_resposta": round(sum(response_days) / len(response_days), 1) if response_days else 0,
    }
