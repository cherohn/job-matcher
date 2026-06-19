import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPORT_DIR = Path(__file__).parent.parent / "reports"


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


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

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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
    return json_path, md_path
