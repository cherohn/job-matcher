import json
from datetime import datetime
from pathlib import Path

from core.user_config import get_cache_path


LEGACY_CACHE_FILE = Path(__file__).parent.parent / ".job_cache.json"
CACHE_FILE = get_cache_path()


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


def _save(cache: dict):
    tmp_path = CACHE_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(CACHE_FILE)


def is_seen(job_id: str) -> bool:
    return job_id in _load()


def mark_seen(job_id: str, score: int):
    cache = _load()
    cache[job_id] = {
        "score": score,
        "seen_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save(cache)


def get_stats() -> dict:
    cache = _load()
    scores = [v["score"] for v in cache.values() if "score" in v]
    return {
        "total_analisadas": len(cache),
        "score_medio": round(sum(scores) / len(scores), 1) if scores else 0,
        "notificadas": sum(1 for v in cache.values() if v.get("score", 0) >= 80),
        "cache_path": str(CACHE_FILE),
    }
