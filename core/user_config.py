import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from core.secure_store import protect_config_for_disk, reveal_config_from_disk


APP_NAME = "JobMatcher"


def get_app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        fallback = Path.cwd() / "user_data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def get_cache_path() -> Path:
    return get_app_data_dir() / "job_cache.json"


def get_documents_dir() -> Path:
    path = get_app_data_dir() / "documents"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_user_config() -> Dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return reveal_config_from_disk(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_user_config(data: Dict[str, Any]) -> Path:
    path = get_config_path()
    current = load_user_config()
    current.update({key: value for key, value in data.items() if value is not None})
    disk_data = protect_config_for_disk(current)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(disk_data, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp_path.read_text(encoding="utf-8"))
    tmp_path.replace(path)
    return path


def import_user_file(source_path: str, target_name: Optional[str] = None) -> str:
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(source_path)
    safe_name = target_name or source.name
    target = get_documents_dir() / safe_name
    shutil.copy2(source, target)
    return str(target)


def is_configured(config: Optional[Dict[str, Any]] = None) -> bool:
    data = config if config is not None else load_user_config()
    required = [
        "groq_api_key",
        "serper_api_key",
        "email_remetente",
        "email_senha_app",
        "email_destinatario",
    ]
    has_credentials = all(str(data.get(key, "")).strip() for key in required)
    has_profile = bool(str(data.get("profile_text", "")).strip() or str(data.get("profile_text_path", "")).strip())
    has_resume = bool(str(data.get("resume_pdf_path", "")).strip())
    return has_credentials and (has_profile or has_resume)
