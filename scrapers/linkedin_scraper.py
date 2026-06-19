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


def fetch_linkedin_jobs(queries: List[str], location: str = "Brasil") -> List[Job]:
    """Fetch public LinkedIn job results without using a logged-in session."""
    jobs = []
    seen_ids = set()

    for query in queries:
        query_encoded = query.replace(" ", "%20")
        location_encoded = location.replace(" ", "%20")
        url = (
            f"https://www.linkedin.com/jobs/search/?keywords={query_encoded}"
            f"&location={location_encoded}&f_TPR=r86400"
        )

        feed = feedparser.parse(url)

        for entry in feed.entries:
            job_url = entry.get("link", "")
            if not job_url:
                continue
            job_id = _make_id(job_url)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            title = entry.get("title", "Sem titulo")
            company = "Nao informado"
            if " - " in title:
                parts = title.split(" - ", 1)
                title = parts[0].strip()
                company = parts[1].strip()

            description = _clean_html(entry.get("summary", "") or entry.get("description", ""))

            jobs.append(Job(
                id=job_id,
                title=title,
                company=company,
                location=location,
                description=description[:3000],
                url=job_url,
                source="LinkedIn",
            ))

    return jobs
