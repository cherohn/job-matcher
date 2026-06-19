import smtplib
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape


@dataclass
class JobAlert:
    title: str
    company: str
    location: str
    url: str
    source: str
    score: int
    pontos_fortes: list[str]
    gaps: list[str]
    resumo: str
    curriculo_foco: list[str] = field(default_factory=list)
    curriculo_ajustes: list[str] = field(default_factory=list)
    curriculo_headline: str = ""


def _color(score: int) -> str:
    if score >= 90:
        return "#16a34a"
    if score >= 85:
        return "#22c55e"
    return "#3b82f6"


def _badge(score: int) -> str:
    if score >= 90:
        return "Match forte"
    if score >= 85:
        return "Bom match"
    return "Match possivel"


def _items(values: list[str], empty: str) -> str:
    values = [escape(str(value)) for value in values if str(value).strip()]
    if not values:
        return f"<li>{escape(empty)}</li>"
    return "".join(f"<li>{value}</li>" for value in values)


def _build_card(a: JobAlert, compact: bool = False) -> str:
    c = _color(a.score)
    btn = f'<p><a href="{escape(a.url)}" style="color:#2563eb;font-weight:bold;">Abrir vaga</a></p>' if a.url else ""
    return f"""
    <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:0 0 16px;background:#ffffff;">
      <p style="margin:0 0 6px;color:{c};font-weight:bold;">{_badge(a.score)} - {a.score}%</p>
      <h3 style="margin:0 0 4px;color:#111827;">{escape(a.title)}</h3>
      <p style="margin:0 0 10px;color:#6b7280;">{escape(a.company)} | {escape(a.location)} | {escape(a.source)}</p>
      <p style="margin:0 0 12px;color:#374151;">{escape(a.resumo)}</p>
      <p style="margin:0 0 4px;"><b>Pontos fortes</b></p>
      <ul style="margin-top:0;">{_items(a.pontos_fortes[:3], "Nenhum ponto forte gerado.")}</ul>
      <p style="margin:0 0 4px;"><b>Gaps</b></p>
      <ul style="margin-top:0;">{_items(a.gaps[:2], "Nenhum gap significativo.")}</ul>
      <p style="margin:0 0 4px;"><b>Curriculo direcionado</b></p>
      <p style="margin:0 0 8px;color:#374151;"><b>Headline:</b> {escape(a.curriculo_headline or "Use uma headline alinhada ao titulo da vaga.")}</p>
      <p style="margin:0 0 4px;">O que destacar:</p>
      <ul style="margin-top:0;">{_items(a.curriculo_foco[:3], "Use os pontos fortes acima como base.")}</ul>
      <p style="margin:0 0 4px;">Ajustes honestos:</p>
      <ul style="margin-top:0;">{_items(a.curriculo_ajustes[:3], "Nenhum ajuste especifico gerado.")}</ul>
      {btn}
    </div>
    """


def _smtp_send(msg: MIMEMultipart, remetente: str, senha_app: str, destinatario: str) -> None:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(remetente, senha_app)
        s.sendmail(remetente, destinatario, msg.as_string())


def send_job_alert(alert: JobAlert, remetente: str, senha_app: str, destinatario: str) -> bool:
    try:
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
        <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
          <div style="max-width:760px;margin:32px auto;padding:24px;">
            <h2 style="margin:0 0 8px;color:#111827;">Job Matcher</h2>
            {_build_card(alert)}
          </div>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Job Matcher - [{alert.score}%] {alert.title} @ {alert.company}"
        msg["From"] = f"Job Matcher <{remetente}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        _smtp_send(msg, remetente, senha_app, destinatario)
        return True
    except Exception as e:
        print(f"[Email] Erro: {e}")
        return False


def send_job_digest(alerts: list[JobAlert], report_path: str, remetente: str, senha_app: str, destinatario: str, min_score: int) -> bool:
    try:
        items = "".join(_build_card(alert, compact=True) for alert in alerts)
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
        <body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif;">
          <div style="max-width:760px;margin:32px auto;padding:24px;">
            <h2 style="margin:0 0 8px;color:#111827;">Job Matcher - matches acima de {min_score}%</h2>
            <p style="color:#6b7280;">Relatorio salvo localmente em: <code>{escape(report_path)}</code></p>
            {items}
          </div>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Job Matcher - {len(alerts)} match(es) acima de {min_score}%"
        msg["From"] = f"Job Matcher <{remetente}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        _smtp_send(msg, remetente, senha_app, destinatario)
        return True
    except Exception as e:
        print(f"[Email] Erro digest: {e}")
        return False


def send_startup_email(remetente: str, senha_app: str, destinatario: str, queries: list, min_score: int):
    try:
        qs = "".join(f"<li>{escape(str(q))}</li>" for q in queries)
        html = f"""<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;padding:24px;">
          <h2>Job Matcher iniciado</h2>
          <p>Monitorando vagas para:</p><ul>{qs}</ul>
          <p><b>Score minimo:</b> {min_score}%</p>
          <p><b>Fonte principal:</b> Google via Serper</p>
          <p style="color:#6b7280;font-size:13px;">Voce recebera um e-mail quando encontrar vagas compativeis.</p>
        </div>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Job Matcher - monitoramento iniciado"
        msg["From"] = f"Job Matcher <{remetente}>"
        msg["To"] = destinatario
        msg.attach(MIMEText(html, "html", "utf-8"))
        _smtp_send(msg, remetente, senha_app, destinatario)
    except Exception as e:
        print(f"[Email] Erro startup: {e}")
