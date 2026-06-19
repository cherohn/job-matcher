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


def fetch_indeed_jobs(queries: List[str], location: str = "Brasil") -> List[Job]:
    jobs = []
    seen_ids = set()

    for query in queries:
        rss_url = (
            f"https://br.indeed.com/rss?q={query.replace(' ', '+')}"
            f"&l={location.replace(' ', '+')}&sort=date&fromage=1"
        )
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue
            job_id = _make_id(url)
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            description = _clean_html(entry.get("summary", "") or entry.get("description", ""))

            jobs.append(Job(
                id=job_id,
                title=entry.get("title", "Sem titulo"),
                company=entry.get("author", "Nao informado"),
                location=location,
                description=description[:3000],
                url=url,
                source="Indeed",
            ))

    return jobs
