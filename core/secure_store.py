import base64
import ctypes
import sys
from ctypes import wintypes
from typing import Optional


SENSITIVE_FIELDS = {
    "groq_api_key",
    "serper_api_key",
    "email_senha_app",
}


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def can_encrypt() -> bool:
    return sys.platform == "win32"


def encrypt_text(value: str) -> Optional[str]:
    if not can_encrypt() or not value:
        return None

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    data = value.encode("utf-8")
    in_blob = _blob_from_bytes(data)
    out_blob = DATA_BLOB()

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "JobMatcher",
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        return None

    try:
        encrypted = _bytes_from_blob(out_blob)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def decrypt_text(value: str) -> Optional[str]:
    if not can_encrypt() or not value:
        return None

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    try:
        encrypted = base64.b64decode(value.encode("ascii"))
    except Exception:
        return None

    in_blob = _blob_from_bytes(encrypted)
    out_blob = DATA_BLOB()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        return None

    try:
        return _bytes_from_blob(out_blob).decode("utf-8")
    finally:
        kernel32.LocalFree(out_blob.pbData)


def protect_config_for_disk(data: dict) -> dict:
    protected = dict(data)
    for key in SENSITIVE_FIELDS:
        value = protected.get(key)
        if not isinstance(value, str) or not value:
            continue
        encrypted = encrypt_text(value)
        if encrypted:
            protected[key] = {
                "__secure__": "windows-dpapi",
                "value": encrypted,
            }
    return protected


def reveal_config_from_disk(data: dict) -> dict:
    revealed = dict(data)
    for key in SENSITIVE_FIELDS:
        value = revealed.get(key)
        if not isinstance(value, dict):
            continue
        if value.get("__secure__") != "windows-dpapi":
            continue
        decrypted = decrypt_text(str(value.get("value", "")))
        revealed[key] = decrypted or ""
    return revealed
