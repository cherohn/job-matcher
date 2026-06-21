import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

from core.user_config import get_cache_path


LEGACY_CACHE_FILE = Path(__file__).parent.parent / ".job_cache.json"
CACHE_FILE = get_cache_path()
SIGNATURES_KEY = "__job_signatures__"
DEFAULT_SIGNATURE_TTL_DAYS = 30


def _migrate_legacy_cache() -> None:
    if CACHE_FILE.exists() or not LEGACY_CACHE_FILE.exists():
        return
    try:
        CACHE_FILE.write_text(LEGACY_CACHE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass


def _load() -> dict:
    _migrate_legacy_cache()
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _parse_datetime(value: str):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _normalize_location(location: str) -> str:
    normalized = _normalize_text(location)
    replacements = {
        "sao paulo sp brasil": "sao paulo sp brasil",
        "sao paulo brasil": "sao paulo brasil",
        "sp brasil": "sp brasil",
        "rio de janeiro rj brasil": "rio de janeiro rj brasil",
        "rio de janeiro brasil": "rio de janeiro brasil",
        "rj brasil": "rj brasil",
        "remoto brasil": "remoto brasil",
        "remote brazil": "remoto brasil",
        "home office brasil": "remoto brasil",
    }
    return replacements.get(normalized, normalized)


def job_signature(title: str, company: str = "", source: str = "", location: str = "") -> str:
    parts = [
        _normalize_text(title),
        _normalize_text(company),
        _normalize_text(source),
        _normalize_location(location),
    ]
    parts = [part for part in parts if part]
    return "|".join(parts)


def _prune_signatures(cache: dict, ttl_days: int = DEFAULT_SIGNATURE_TTL_DAYS) -> int:
    signatures = cache.get(SIGNATURES_KEY)
    if not isinstance(signatures, dict):
        cache[SIGNATURES_KEY] = {}
        return 0

    cutoff = datetime.now() - timedelta(days=ttl_days)
    removed = 0
    for signature, data in list(signatures.items()):
        if not isinstance(data, dict):
            signatures.pop(signature, None)
            removed += 1
            continue
        last_seen = _parse_datetime(data.get("seen_at"))
        if last_seen is None or last_seen < cutoff:
            signatures.pop(signature, None)
            removed += 1
    return removed


def _save(cache: dict):
    _prune_signatures(cache)
    tmp_path = CACHE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(CACHE_FILE)


def is_seen(job_id: str) -> bool:
    return job_id in _load()


def is_recent_job(job, ttl_days: int = DEFAULT_SIGNATURE_TTL_DAYS) -> bool:
    cache = _load()
    changed = _prune_signatures(cache, ttl_days)

    job_id = getattr(job, "id", "")
    if job_id and job_id in cache:
        if changed:
            _save(cache)
        return True

    signature = job_signature(
        getattr(job, "title", ""),
        getattr(job, "company", ""),
        getattr(job, "source", ""),
        getattr(job, "location", ""),
    )
    if not signature:
        if changed:
            _save(cache)
        return False

    signatures = cache.get(SIGNATURES_KEY, {})
    data = signatures.get(signature)
    if not isinstance(data, dict):
        if changed:
            _save(cache)
        return False

    last_seen = _parse_datetime(data.get("seen_at"))
    if last_seen and last_seen >= datetime.now() - timedelta(days=ttl_days):
        if changed:
            _save(cache)
        return True

    signatures.pop(signature, None)
    _save(cache)
    return False


def mark_seen(job_id: str, score: int, job=None):
    cache = _load()
    _prune_signatures(cache)
    cache[job_id] = {
        "score": score,
        "seen_at": datetime.now().isoformat(timespec="seconds"),
    }
    if job is not None:
        signature = job_signature(
            getattr(job, "title", ""),
            getattr(job, "company", ""),
            getattr(job, "source", ""),
            getattr(job, "location", ""),
        )
        if signature:
            cache.setdefault(SIGNATURES_KEY, {})[signature] = {
                "title": getattr(job, "title", ""),
                "company": getattr(job, "company", ""),
                "source": getattr(job, "source", ""),
                "location": getattr(job, "location", ""),
                "job_id": job_id,
                "score": score,
                "seen_at": datetime.now().isoformat(timespec="seconds"),
                "expires_at": (datetime.now() + timedelta(days=DEFAULT_SIGNATURE_TTL_DAYS)).isoformat(timespec="seconds"),
            }
    _save(cache)


def get_stats() -> dict:
    cache = _load()
    _prune_signatures(cache)
    signatures = cache.get(SIGNATURES_KEY, {})
    scores = [v["score"] for key, v in cache.items() if key != SIGNATURES_KEY and isinstance(v, dict) and "score" in v]
    return {
        "total_analisadas": sum(1 for key in cache if key != SIGNATURES_KEY),
        "score_medio": round(sum(scores) / len(scores), 1) if scores else 0,
        "notificadas": sum(1 for key, v in cache.items() if key != SIGNATURES_KEY and isinstance(v, dict) and v.get("score", 0) >= 80),
        "bloqueadas_30d": len(signatures) if isinstance(signatures, dict) else 0,
        "cache_path": str(CACHE_FILE),
    }
