import re
from pathlib import Path
from typing import Optional


def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(pdf_path)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()
    except ImportError:
        print("[ResumeParser] Instale: pip install pdfminer.six")
        return None
    except Exception as e:
        print(f"[ResumeParser] Erro ao ler PDF: {e}")
        return None


def extract_text_from_txt(txt_path: str) -> Optional[str]:
    try:
        text = Path(txt_path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = Path(txt_path).read_text(encoding="latin-1")
    except Exception as e:
        print(f"[ResumeParser] Erro ao ler TXT: {e}")
        return None

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def build_profile(
    profile_text: str,
    pdf_path: Optional[str] = None,
    profile_text_path: Optional[str] = None,
) -> str:
    parts = []
    if pdf_path and Path(pdf_path).exists():
        pdf_text = extract_text_from_pdf(pdf_path)
        if pdf_text:
            parts.append("=== CURRICULO (PDF) ===\n" + pdf_text[:4000])

    if profile_text_path and Path(profile_text_path).exists():
        txt_text = extract_text_from_txt(profile_text_path)
        if txt_text:
            parts.append("=== PERFIL DETALHADO (TXT) ===\n" + txt_text[:8000])

    if profile_text and profile_text.strip():
        parts.append("=== PERFIL DETALHADO ===\n" + profile_text.strip())

    if not parts:
        raise ValueError("Nenhum perfil disponivel. Configure um TXT de perfil, texto de perfil ou PDF.")

    return "\n\n".join(parts)
