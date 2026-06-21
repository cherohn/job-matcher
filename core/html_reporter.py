import html
import re
import unicodedata
import webbrowser
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


REPORTS_ROOT = Path(__file__).parent.parent / "reports"
REPORT_FOLDERS = {
    "vagas": REPORTS_ROOT / "vagas",
    "ats": REPORTS_ROOT / "ats",
    "cartas": REPORTS_ROOT / "cartas",
    "tendencias": REPORTS_ROOT / "tendencias",
}

IRON_COLORS = {
    "bg": "#0F0F0F",
    "base": "#181818",
    "surface": "#202020",
    "surface_2": "#2A2A2A",
    "border": "#303030",
    "accent": "#C49A3C",
    "accent_dim": "#8E6E2B",
    "text": "#DCDCDC",
    "muted": "#8A8A8A",
    "danger": "#9E3B3B",
    "danger_bg": "#3A1B1B",
    "success": "#3FA66B",
    "success_bg": "#173522",
    "warning": "#D6A83B",
    "warning_bg": "#3A2D14",
}


def ensure_report_dirs() -> None:
    REPORTS_ROOT.mkdir(exist_ok=True)
    for folder in REPORT_FOLDERS.values():
        folder.mkdir(parents=True, exist_ok=True)


def slugify(text: str, fallback: str = "relatorio") -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug[:80] or fallback


def open_html_report(path: Path) -> None:
    webbrowser.open(path.resolve().as_uri())


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _paragraphs(text: str) -> str:
    chunks = [chunk.strip() for chunk in str(text or "").splitlines() if chunk.strip()]
    if not chunks:
        return '<p class="muted">Nenhum texto informado.</p>'
    return "\n".join(f"<p>{_e(chunk)}</p>" for chunk in chunks)


def _list_block(items: Iterable[str], empty: str = "Nenhum ponto especifico identificado.") -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return f'<p class="muted">{_e(empty)}</p>'
    return "<ul class=\"clean-list\">" + "".join(f"<li>{_e(item)}</li>" for item in values) + "</ul>"


def _tag_list(items: Iterable[str], kind: str = "neutral", empty: str = "Nenhum item encontrado.") -> str:
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return f'<p class="muted">{_e(empty)}</p>'
    return '<div class="tag-list">' + "".join(f'<span class="tag tag-{kind}">{_e(item)}</span>' for item in values) + "</div>"


def _metric_card(label: str, value: Any, detail: str = "") -> str:
    detail_html = f'<span class="metric-detail">{_e(detail)}</span>' if detail else ""
    return (
        '<article class="metric-card">'
        f'<span class="metric-label">{_e(label)}</span>'
        f'<strong>{_e(value)}</strong>'
        f"{detail_html}"
        "</article>"
    )


BASE_CSS = f"""
:root {{
  --bg: {IRON_COLORS["bg"]};
  --base: {IRON_COLORS["base"]};
  --surface: {IRON_COLORS["surface"]};
  --surface-2: {IRON_COLORS["surface_2"]};
  --border: {IRON_COLORS["border"]};
  --accent: {IRON_COLORS["accent"]};
  --accent-dim: {IRON_COLORS["accent_dim"]};
  --text: {IRON_COLORS["text"]};
  --muted: {IRON_COLORS["muted"]};
  --danger: {IRON_COLORS["danger"]};
  --danger-bg: {IRON_COLORS["danger_bg"]};
  --success: {IRON_COLORS["success"]};
  --success-bg: {IRON_COLORS["success_bg"]};
  --warning: {IRON_COLORS["warning"]};
  --warning-bg: {IRON_COLORS["warning_bg"]};
  color-scheme: dark;
}}

* {{
  box-sizing: border-box;
}}

html {{
  background: var(--bg);
}}

body {{
  margin: 0;
  min-height: 100vh;
  background:
    linear-gradient(180deg, rgba(196, 154, 60, 0.07), transparent 260px),
    var(--bg);
  color: var(--text);
  font-family: "Segoe UI", Inter, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 16px;
  line-height: 1.55;
}}

a {{
  color: var(--accent);
  text-decoration: none;
}}

.page {{
  width: min(1120px, calc(100vw - 40px));
  margin: 0 auto;
  padding: 38px 0 54px;
}}

.hero {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: end;
  padding: 0 0 26px;
  border-bottom: 1px solid var(--border);
}}

.eyebrow {{
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  margin-bottom: 14px;
  padding: 4px 10px;
  border: 1px solid rgba(196, 154, 60, 0.42);
  border-radius: 999px;
  background: rgba(196, 154, 60, 0.12);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}}

h1, h2, h3, p {{
  margin-top: 0;
}}

h1 {{
  max-width: 840px;
  margin-bottom: 10px;
  color: #F2F2F2;
  font-size: clamp(34px, 5vw, 58px);
  line-height: 1.02;
  letter-spacing: 0;
}}

.subtitle {{
  max-width: 820px;
  margin: 0;
  color: var(--muted);
  font-size: 17px;
}}

.stamp {{
  color: var(--muted);
  font-size: 13px;
  text-align: right;
}}

.grid {{
  display: grid;
  gap: 16px;
}}

.grid-2 {{
  grid-template-columns: repeat(2, minmax(0, 1fr));
}}

.grid-3 {{
  grid-template-columns: repeat(3, minmax(0, 1fr));
}}

.section {{
  padding: 28px 0 0;
}}

.section-title {{
  margin-bottom: 12px;
  color: #F0F0F0;
  font-size: 21px;
  line-height: 1.2;
}}

.card,
.metric-card {{
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--base);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.28);
}}

.card {{
  padding: 20px;
}}

.card h3 {{
  margin-bottom: 10px;
  color: #EFEFEF;
  font-size: 16px;
}}

.metric-card {{
  min-height: 116px;
  padding: 18px;
}}

.metric-label,
.metric-detail,
.muted {{
  color: var(--muted);
}}

.metric-label,
.metric-detail {{
  display: block;
  font-size: 12px;
}}

.metric-card strong {{
  display: block;
  margin: 5px 0;
  color: #F5F5F5;
  font-size: 34px;
  line-height: 1;
}}

.clean-list {{
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}}

.clean-list li {{
  position: relative;
  padding-left: 18px;
  color: #DADADA;
}}

.clean-list li::before {{
  content: "";
  position: absolute;
  left: 0;
  top: 0.72em;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}}

.tag-list {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}}

.tag {{
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  font-weight: 650;
}}

.tag-success {{
  border-color: rgba(63, 166, 107, 0.42);
  background: var(--success-bg);
  color: #BCE8CC;
}}

.tag-danger {{
  border-color: rgba(158, 59, 59, 0.5);
  background: var(--danger-bg);
  color: #F0C0C0;
}}

.tag-warning {{
  border-color: rgba(214, 168, 59, 0.45);
  background: var(--warning-bg);
  color: #F1D38B;
}}

.score {{
  color: var(--accent);
}}

.progress {{
  width: 100%;
  height: 12px;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
}}

.progress span {{
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}}

.letter {{
  max-width: 820px;
  color: #EEEEEE;
  font-size: 18px;
  line-height: 1.72;
}}

.bar-row {{
  display: grid;
  grid-template-columns: minmax(130px, 220px) 1fr 64px;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}}

.bar-track {{
  height: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--surface);
}}

.bar-track span {{
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}}

.pre-wrap {{
  white-space: pre-wrap;
}}

@media (max-width: 760px) {{
  .page {{
    width: min(100vw - 28px, 1120px);
    padding-top: 26px;
  }}

  .hero,
  .grid-2,
  .grid-3 {{
    grid-template-columns: 1fr;
  }}

  .stamp {{
    text-align: left;
  }}

  h1 {{
    font-size: 34px;
  }}

  .bar-row {{
    grid-template-columns: 1fr;
    gap: 6px;
  }}
}}
"""


def render_document(title: str, subtitle: str, body_html: str, eyebrow: str = "Job Matcher") -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)} | Job Matcher</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <main class="page">
    <header class="hero">
      <div>
        <span class="eyebrow">{_e(eyebrow)}</span>
        <h1>{_e(title)}</h1>
        <p class="subtitle">{_e(subtitle)}</p>
      </div>
      <div class="stamp">Gerado em<br>{_e(now)}</div>
    </header>
    {body_html}
  </main>
</body>
</html>
"""


def save_html_report(
    folder: str,
    filename_base: str,
    title: str,
    subtitle: str,
    body_html: str,
    eyebrow: str = "Job Matcher",
    open_browser: bool = False,
) -> Path:
    ensure_report_dirs()
    directory = REPORT_FOLDERS.get(folder, REPORTS_ROOT / folder)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slugify(filename_base)}.html"
    path.write_text(render_document(title, subtitle, body_html, eyebrow), encoding="utf-8")
    if open_browser:
        open_html_report(path)
    return path


def generate_job_analysis_report(
    job_title: str,
    job_company: str,
    job_description: str,
    analysis: Any,
    filename_base: str | None = None,
    open_browser: bool = False,
) -> Path:
    data = _plain(analysis)
    title = job_title or "Vaga analisada"
    company = job_company or "Empresa nao informada"
    score = max(0, min(100, int(data.get("score", 0) or 0)))
    priority = str(data.get("prioridade_ajuste", "media") or "media").lower()
    priority_kind = "danger" if priority == "alta" else "warning" if priority == "media" else "success"
    base = filename_base or f"vaga-{company}-{title}"

    body = f"""
    <section class="section grid grid-3">
      {_metric_card("Score de compatibilidade", f"{score}%", "Regua da analise de vaga")}
      {_metric_card("Prioridade de ajuste", priority.title(), "Antes de se candidatar")}
      {_metric_card("Empresa", company, title)}
    </section>

    <section class="section">
      <div class="card">
        <h2 class="section-title">Veredito</h2>
        <p>{_e(data.get("veredito") or "Nao informado.")}</p>
        <div class="progress" aria-label="Score de compatibilidade"><span style="width: {score}%"></span></div>
      </div>
    </section>

    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Pontos fortes</h2>
        {_list_block(_items(data.get("pontos_fortes")))}
      </article>
      <article class="card">
        <h2 class="section-title">Gaps e pontos fracos</h2>
        {_list_block(_items(data.get("pontos_fracos")))}
      </article>
    </section>

    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Melhorias no curriculo</h2>
        {_list_block(_items(data.get("melhorias_curriculo")))}
      </article>
      <article class="card">
        <h2 class="section-title">Menos destaque</h2>
        {_list_block(_items(data.get("itens_menos_relevantes")))}
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Proxima acao</h2>
        <div class="tag-list"><span class="tag tag-{priority_kind}">{_e(data.get("proxima_acao") or "Nao informada.")}</span></div>
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Descricao da vaga</h2>
        <div class="pre-wrap muted">{_e(job_description)}</div>
      </article>
    </section>
    """
    return save_html_report(
        "vagas",
        base,
        title if not job_company else f"{title} @ {job_company}",
        "Analise visual gerada a partir do score, pontos fortes, gaps e recomendacoes.",
        body,
        eyebrow="Analise de vaga",
        open_browser=open_browser,
    )


def generate_resume_optimization_report(
    job_title: str,
    job_company: str,
    job_description: str,
    optimization: Any,
    filename_base: str | None = None,
    open_browser: bool = False,
) -> Path:
    data = _plain(optimization)
    title = job_title or "Vaga alvo"
    company = job_company or "Empresa nao informada"
    base = filename_base or f"otimizacao-{company}-{title}"

    body = f"""
    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Headline sugerida</h2>
        <p>{_e(data.get("headline_sugerida") or "Nao gerada.")}</p>
      </article>
      <article class="card">
        <h2 class="section-title">Proxima acao</h2>
        <p>{_e(data.get("proxima_acao") or "Nao informada.")}</p>
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Resumo profissional sugerido</h2>
        {_paragraphs(data.get("resumo_profissional_sugerido") or "")}
      </article>
    </section>

    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Skills prioritarias</h2>
        {_tag_list(_items(data.get("skills_prioritarias")), "success")}
      </article>
      <article class="card">
        <h2 class="section-title">Experiencias para priorizar</h2>
        {_list_block(_items(data.get("experiencias_prioritarias")))}
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Bullets sugeridos</h2>
        {_list_block(_items(data.get("bullets_sugeridos")))}
      </article>
    </section>

    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Reduzir ou remover destaque</h2>
        {_list_block(_items(data.get("reduzir_ou_remover")))}
      </article>
      <article class="card">
        <h2 class="section-title">Evidencias ausentes</h2>
        {_tag_list(_items(data.get("evidencias_ausentes")), "warning")}
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Avisos de honestidade</h2>
        {_list_block(_items(data.get("avisos_honestidade")))}
      </article>
    </section>

    <section class="section">
      <article class="card">
        <h2 class="section-title">Descricao da vaga</h2>
        <div class="pre-wrap muted">{_e(job_description)}</div>
      </article>
    </section>
    """
    return save_html_report(
        "vagas",
        base,
        f"Otimizacao para {title}",
        f"Direcionamento do curriculo para {company}, mantendo a regra de nao inventar experiencia.",
        body,
        eyebrow="Otimizacao de curriculo",
        open_browser=open_browser,
    )


def generate_scan_report(
    collected_jobs: list[Any],
    analyzed_jobs: list[Mapping[str, Any]],
    min_score: int,
    filename_base: str,
    open_browser: bool = False,
) -> Path:
    analyzed_sorted = sorted(analyzed_jobs, key=lambda item: item.get("score", 0), reverse=True)
    matches = [item for item in analyzed_sorted if int(item.get("score", 0) or 0) >= min_score]

    rows = []
    for item in analyzed_sorted:
        score = max(0, min(100, int(item.get("score", 0) or 0)))
        title = item.get("title") or "Sem titulo"
        company = item.get("company") or "Nao informado"
        source = item.get("source") or "Nao informado"
        location = item.get("location") or "Nao informado"
        url = item.get("url") or ""
        gaps = _items(item.get("gaps"))
        strengths = _items(item.get("pontos_fortes"))
        score_kind = "success" if score >= min_score else "warning" if score >= 60 else "danger"
        link = f'<a href="{_e(url)}" target="_blank" rel="noreferrer">Abrir vaga</a>' if url else '<span class="muted">Sem URL</span>'
        rows.append(f"""
        <article class="card">
          <div class="grid grid-2">
            <div>
              <span class="tag tag-{score_kind}">{score}%</span>
              <h2 class="section-title" style="margin-top: 12px">{_e(title)}</h2>
              <p class="muted">{_e(company)} | {_e(source)} | {_e(location)}</p>
              <p>{_e(item.get("resumo") or "Sem resumo.")}</p>
              {link}
            </div>
            <div>
              <h3>Pontos fortes</h3>
              {_list_block(strengths)}
              <h3 style="margin-top: 18px">Gaps</h3>
              {_list_block(gaps, "Nenhum gap informado.")}
            </div>
          </div>
        </article>
        """)

    jobs_html = "\n".join(rows) or """
    <article class="card">
      <h2 class="section-title">Nenhuma vaga analisada</h2>
      <p class="muted">A varredura coletou vagas, mas nenhuma chegou a ser analisada nesta execucao.</p>
    </article>
    """

    body = f"""
    <section class="section grid grid-3">
      {_metric_card("Coletadas", len(collected_jobs), "Antes dos filtros locais")}
      {_metric_card("Analisadas", len(analyzed_sorted), "Comparadas com o perfil")}
      {_metric_card("Matches", len(matches), f"Score minimo: {min_score}%")}
    </section>

    <section class="section">
      <h2 class="section-title">Vagas analisadas</h2>
      <div class="grid">
        {jobs_html}
      </div>
    </section>
    """
    return save_html_report(
        "scan",
        filename_base,
        "Varredura de vagas",
        "Resumo visual das vagas coletadas, analisadas e aprovadas pelo score minimo.",
        body,
        eyebrow="Varredura",
        open_browser=open_browser,
    )


def generate_ats_report(data: Mapping[str, Any], filename_base: str, open_browser: bool = False) -> Path:
    score = max(0, min(100, int(data.get("coverage_score", data.get("score", 0)) or 0)))
    risk = "baixo" if score > 70 else "medio" if score >= 50 else "alto"
    risk_kind = "success" if risk == "baixo" else "warning" if risk == "medio" else "danger"
    present = _items(data.get("keywords_presentes") or data.get("keywords_found"))
    missing = _items(data.get("keywords_ausentes") or data.get("keywords_missing"))
    warnings = _items(data.get("avisos_pdf") or data.get("warnings"))

    body = f"""
    <section class="section grid grid-3">
      {_metric_card("Cobertura ATS", f"{score}%", "Keywords da vaga no curriculo")}
      {_metric_card("Risco", risk.title(), "Leitura automatica")}
      {_metric_card("Keywords ausentes", len(missing), "Prioridade de ajuste")}
    </section>
    <section class="section">
      <article class="card">
        <h2 class="section-title">Diagnostico</h2>
        <p>{_e(data.get("diagnostico") or data.get("diagnosis") or "Nao informado.")}</p>
        <div class="progress"><span style="width: {score}%; background: var(--{risk_kind})"></span></div>
      </article>
    </section>
    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Presentes no curriculo</h2>
        {_tag_list(present, "success", "Nenhuma keyword encontrada.")}
      </article>
      <article class="card">
        <h2 class="section-title">Ausentes no curriculo</h2>
        {_tag_list(missing, "danger", "Nenhuma keyword ausente.")}
      </article>
    </section>
    <section class="section">
      <article class="card">
        <h2 class="section-title">Avisos de formato</h2>
        {_list_block(warnings, "Nenhum problema de formato detectado.")}
      </article>
    </section>
    """
    return save_html_report(
        "ats",
        filename_base,
        data.get("title") or "Simulacao ATS",
        "Leitura do curriculo como um filtro automatico provavelmente enxergaria.",
        body,
        eyebrow="ATS",
        open_browser=open_browser,
    )


def generate_cover_letter_report(data: Mapping[str, Any], filename_base: str, open_browser: bool = False) -> Path:
    letter = str(data.get("carta") or data.get("letter") or "").strip()
    warnings = _items(data.get("avisos") or data.get("warnings"))
    word_count = data.get("word_count") or len(re.findall(r"\S+", letter))
    language = data.get("idioma") or data.get("language") or "Nao informado"

    body = f"""
    <section class="section grid grid-3">
      {_metric_card("Idioma detectado", language)}
      {_metric_card("Palavras", word_count, "Limite recomendado: 250")}
      {_metric_card("Avisos", len(warnings), "Revisar antes de enviar")}
    </section>
    <section class="section">
      <article class="card">
        <h2 class="section-title">Carta</h2>
        <div class="letter">{_paragraphs(letter)}</div>
      </article>
    </section>
    <section class="section grid grid-2">
      <article class="card">
        <h2 class="section-title">Avisos</h2>
        {_list_block(warnings, "Nenhum aviso local encontrado.")}
      </article>
      <article class="card">
        <h2 class="section-title">Como usar</h2>
        <p>Copie a carta, revise qualquer trecho marcado com [REVISAR] e cole no formulario ou e-mail da candidatura.</p>
      </article>
    </section>
    """
    return save_html_report(
        "cartas",
        filename_base,
        data.get("title") or "Carta de apresentacao",
        "Carta contextualizada para a vaga, pronta para revisar e copiar.",
        body,
        eyebrow="Carta",
        open_browser=open_browser,
    )


def generate_market_trends_report(data: Mapping[str, Any], filename_base: str, open_browser: bool = False) -> Path:
    technologies = list(data.get("technologies") or data.get("tecnologias") or [])
    gaps = _items(data.get("skill_gaps") or data.get("gaps"))

    bars = []
    for item in technologies[:15]:
        if isinstance(item, Mapping):
            name = item.get("name") or item.get("tecnologia") or item.get("tech")
            pct = int(item.get("percent") or item.get("percentual") or item.get("value") or 0)
        else:
            name, pct = str(item), 0
        pct = max(0, min(100, pct))
        bars.append(
            f'<div class="bar-row"><strong>{_e(name)}</strong><div class="bar-track">'
            f'<span style="width: {pct}%"></span></div><span class="muted">{pct}%</span></div>'
        )
    bars_html = "".join(bars) or '<p class="muted">Nenhuma tecnologia agregada ainda.</p>'

    body = f"""
    <section class="section grid grid-3">
      {_metric_card("Vagas analisadas", data.get("total_jobs") or data.get("total_vagas") or 0)}
      {_metric_card("Processadas com sucesso", data.get("processed_success") or data.get("sucesso") or 0)}
      {_metric_card("Periodo", data.get("period") or data.get("periodo") or "Nao informado")}
    </section>
    <section class="section">
      <article class="card">
        <h2 class="section-title">Top tecnologias</h2>
        {bars_html}
      </article>
    </section>
    <section class="section">
      <article class="card">
        <h2 class="section-title">Gaps criticos</h2>
        {_tag_list(gaps, "warning", "Nenhum gap critico identificado.")}
      </article>
    </section>
    """
    return save_html_report(
        "tendencias",
        filename_base,
        data.get("title") or "Tendencias de mercado",
        "Resumo visual do historico de vagas coletadas pelo Job Matcher.",
        body,
        eyebrow="Mercado",
        open_browser=open_browser,
    )
