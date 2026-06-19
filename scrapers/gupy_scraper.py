import hashlib
from dataclasses import dataclass
from typing import List

import requests


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def fetch_gupy_jobs(queries: List[str], location: str = "Brasil") -> List[Job]:
    jobs = []
    seen_ids = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobMatcher/1.0)",
        "Accept": "application/json",
    }

    for query in queries:
        try:
            response = requests.get(
                "https://portal.gupy.io/api/v1/jobs",
                params={
                    "jobName": query,
                    "limit": 20,
                    "offset": 0,
                    "sortBy": "publishedDate",
                    "sortOrder": "desc",
                },
                headers=headers,
                timeout=10,
            )
            if response.status_code != 200:
                print(f"[Gupy] Erro {response.status_code} para '{query}'")
                continue

            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                print(f"[Gupy] Resposta nao-JSON para '{query}'")
                continue

            for vaga in response.json().get("data", []):
                url = vaga.get("jobUrl") or f"https://portal.gupy.io/job/{vaga.get('id', '')}"
                job_id = _make_id(url)
                if job_id in seen_ids:
                    continue
                seen_ids.add(job_id)

                desc_parts = []
                for campo in ["description", "responsibilities", "requirements"]:
                    if vaga.get(campo):
                        desc_parts.append(vaga[campo])

                jobs.append(Job(
                    id=job_id,
                    title=vaga.get("name", "Sem titulo"),
                    company=vaga.get("careerPageName", "Nao informado"),
                    location=vaga.get("city", location),
                    description="\n".join(desc_parts)[:3000],
                    url=url,
                    source="Gupy",
                ))

        except requests.RequestException as e:
            print(f"[Gupy] Erro de conexao para '{query}': {e}")

    return jobs
