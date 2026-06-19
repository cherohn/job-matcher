import feedparser
import hashlib
import re
from typing import List

from scrapers.gupy_scraper import Job


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_vagas_jobs(queries: List[str], location: str = "Brasil") -> List[Job]:
    """Fetch public Vagas.com.br RSS results."""
    jobs = []
    seen_ids = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    for query in queries:
        try:
            query_encoded = query.replace(" ", "%20")
            rss_url = f"https://www.vagas.com.br/vagas-de-{query.lower().replace(' ', '-')}?format=rss"
            feed = feedparser.parse(rss_url, request_headers=headers)

            if not feed.entries:
                rss_url = f"https://www.vagas.com.br/vagas?q={query_encoded}&format=rss"
                feed = feedparser.parse(rss_url, request_headers=headers)

            for entry in feed.entries:
                url = entry.get("link", "")
                if not url:
                    continue
                job_id = _make_id(url)
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                title = entry.get("title", "Sem titulo")
                summary = _clean_html(entry.get("summary", "") or entry.get("description", ""))

                company = entry.get("author", "")
                if not company and " - " in title:
                    parts = title.split(" - ", 1)
                    title = parts[0].strip()
                    company = parts[1].strip()
                if not company:
                    company = "Nao informado"

                jobs.append(Job(
                    id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    description=summary[:3000],
                    url=url,
                    source="Vagas.com.br",
                ))

        except Exception as e:
            print(f"[Vagas.com.br] Erro para '{query}': {e}")

    return jobs
