import requests
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

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
    return hashlib.md5(_canonical_url(url).encode()).hexdigest()

def _clean_html(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()

def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("br.linkedin.com", "www.linkedin.com")
    path = parsed.path.rstrip("/")
    query = ""

    if "indeed.com" in host:
        qs = parse_qs(parsed.query)
        if qs.get("jk"):
            query = urlencode({"jk": qs["jk"][0]})

    return urlunparse((parsed.scheme.lower() or "https", host, path, "", query, ""))

def _build_search_query(
    query: str,
    location: str,
    location_filters: Optional[List[str]] = None,
    exclude_terms: Optional[List[str]] = None,
) -> str:
    url_filters = [
        "inurl:linkedin.com/jobs/view",
        "inurl:br.indeed.com/viewjob",
        "inurl:gupy.io/job",
        "inurl:vagas.com.br/vagas/v",
        "inurl:infojobs.com.br/vaga-de",
        "inurl:catho.com.br/vagas/",
    ]
    url_filter = " OR ".join(url_filters)
    loc_filter = location
    if location_filters:
        loc_filter = " OR ".join(f'"{term}"' for term in location_filters)
    active_terms = '"candidate-se" OR "apply" OR "inscreva-se" OR "candidatar-se"'
    exclusions = ""
    if exclude_terms:
        exclusions = " " + " ".join(f'-"{term}"' for term in exclude_terms)
    return f'("{query}" OR {query}) (vaga OR emprego) ({active_terms}) ({loc_filter}) ({url_filter}){exclusions}'

def _is_probably_job_result(title: str, url: str) -> bool:
    title_lower = title.casefold()
    url_lower = url.casefold()

    listing_patterns = [
        r"^\+?\s*de\s+\d+",
        r"^\d+[\d\.\+]*\s+vagas?\s+de",
        r"^\d+[\d\.\+]*\s+.+\s+vagas?\s+em",
        r"^vagas?\s+de\s+",
        r"^vagas?\s+de\s+.+\s+em[: ]",
        r"\bvagas?\s+em\b",
        r"^.+\s+jobs\s+in\s+",
    ]
    if any(re.search(pattern, title_lower) for pattern in listing_patterns):
        return False

    if "linkedin.com/jobs/search" in url_lower:
        return False
    if "br.indeed.com/jobs" in url_lower and "viewjob" not in url_lower:
        return False
    if "vagas.com.br/vagas?" in url_lower:
        return False

    return True

def _matches_location_filter(title: str, snippet: str, url: str, location_filters: Optional[List[str]]) -> bool:
    if not location_filters:
        return True

    haystack = _normalize(f"{title} {snippet} {url}")
    filters = [_normalize(term) for term in location_filters]
    remote_terms = {"remoto", "remote", "home office", "anywhere", "trabalho remoto"}
    florianopolis_terms = {"florianopolis", "floripa"}
    relocation_terms = {"relocation", "reubicacion", "realocacao", "mudanca"}

    has_remote = any(term in haystack for term in remote_terms)
    has_florianopolis = any(term in haystack for term in florianopolis_terms)
    has_relocation = any(term in haystack for term in relocation_terms)

    if has_relocation and not has_remote and not has_florianopolis:
        return False

    if any(term in haystack for term in filters):
        return True
    if has_remote:
        return True
    if has_florianopolis:
        return True

    return False

def _is_active_job_result(title: str, snippet: str, exclude_terms: Optional[List[str]]) -> bool:
    haystack = _normalize(f"{title} {snippet}")
    inactive_terms = [
        "vaga encerrada",
        "vaga expirada",
        "processo encerrado",
        "inscricoes encerradas",
        "inscrições encerradas",
        "nao aceita mais candidaturas",
        "não aceita mais candidaturas",
        "no longer accepting applications",
        "job expired",
        "job closed",
        "position closed",
        "closed position",
        "encerrada",
        "expirada",
    ]
    inactive_terms.extend(exclude_terms or [])
    return not any(_normalize(term) in haystack for term in inactive_terms)

def _has_active_apply_signal(text: str) -> bool:
    haystack = _normalize(text)
    active_terms = [
        "candidate-se",
        "candidatar-se",
        "candidatar",
        "inscreva-se",
        "enviar candidatura",
        "apply",
        "apply now",
        "enviar curriculo",
        "enviar curriculo",
        "quero me candidatar",
    ]
    return any(_normalize(term) in haystack for term in active_terms)

def _page_looks_active(url: str, title: str, snippet: str, exclude_terms: Optional[List[str]]) -> bool:
    if not _is_active_job_result(title, snippet, exclude_terms):
        return False

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobMatcher/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        if response.status_code >= 400:
            return False
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return _has_active_apply_signal(f"{title} {snippet}")
        page_text = _clean_html(response.text[:120000])
        full_text = f"{title} {snippet} {page_text}"
        return _is_active_job_result(title, full_text, exclude_terms) and _has_active_apply_signal(full_text)
    except requests.RequestException:
        return False

def fetch_google_jobs(
    queries: List[str],
    location: str = "Brasil",
    api_key: str = "",
    location_filters: Optional[List[str]] = None,
    exclude_terms: Optional[List[str]] = None,
    date_restrict: str = "m1",
    verify_active_pages: bool = True,
) -> List[Job]:
    """
    Busca vagas no Google via Serper.dev usando o endpoint /search.
    Retorna resultados orgânicos de LinkedIn, Indeed, Gupy e outros sites de vagas.
    """
    jobs = []
    seen_ids = set()
    seen_keys = set()

    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    for query in queries:
        try:
            search_query = _build_search_query(query, location, location_filters, exclude_terms)

            payload = {
                "q": search_query,
                "gl": "br",
                "hl": "pt-br",
                "num": 10,
            }
            if date_restrict:
                payload["dateRestrict"] = date_restrict
                payload["tbs"] = f"qdr:{date_restrict[-1]}"

            response = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=payload,
                timeout=10
            )

            if response.status_code != 200:
                print(f"[Google/Serper] Erro {response.status_code} para '{query}': {response.text[:200]}")
                continue

            data = response.json()
            resultados = data.get("organic", [])

            for item in resultados:
                url = item.get("link", "")
                if not url:
                    continue

                canonical_url = _canonical_url(url)
                job_id = _make_id(canonical_url)
                if job_id in seen_ids:
                    continue

                title   = item.get("title", "Sem título")
                snippet = _clean_html(item.get("snippet", ""))
                if not _is_probably_job_result(title, url):
                    continue
                if not _matches_location_filter(title, snippet, url, location_filters):
                    continue
                if not _is_active_job_result(title, snippet, exclude_terms):
                    continue

                company = "Não informado"
                if " - " in title:
                    parts = title.split(" - ")
                    company = parts[-1].split("|")[0].strip()
                    title   = parts[0].strip()
                elif " | " in title:
                    parts = title.split(" | ")
                    title   = parts[0].strip()
                    company = parts[1].strip() if len(parts) > 1 else company

                source = "Google"
                if "linkedin.com" in url:    source = "LinkedIn"
                elif "gupy.io" in url:       source = "Gupy"
                elif "indeed.com" in url:    source = "Indeed"
                elif "vagas.com.br" in url:  source = "Vagas.com.br"
                elif "catho.com" in url:     source = "Catho"
                elif "infojobs" in url:      source = "InfoJobs"

                duplicate_key = (_normalize(title), _normalize(company), source)
                if duplicate_key in seen_keys:
                    continue

                if verify_active_pages and not _page_looks_active(url, title, snippet, exclude_terms):
                    continue

                seen_ids.add(job_id)
                seen_keys.add(duplicate_key)

                jobs.append(Job(
                    id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    description=snippet[:3000],
                    url=canonical_url,
                    source=source
                ))

        except requests.RequestException as e:
            print(f"[Google/Serper] Erro de conexão para '{query}': {e}")
            continue

    return jobs
