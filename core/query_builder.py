from itertools import product
from typing import Iterable, List


def _clean(value: str) -> str:
    return " ".join(str(value).strip().split())


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = _clean(value)
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def build_search_queries(
    base_terms: Iterable[str],
    seniority_terms: Iterable[str] = (),
    work_modes: Iterable[str] = (),
    companies: Iterable[str] = (),
    manual_queries: Iterable[str] = (),
    max_queries: int = 50,
) -> List[str]:
    """
    Generates broad-to-specific search terms without forcing every word into
    every query. Portals usually match better with shorter terms first.
    """
    base_terms = _dedupe(base_terms)
    seniority_terms = _dedupe(seniority_terms)
    work_modes = _dedupe(work_modes)
    companies = _dedupe(companies)
    manual_queries = _dedupe(manual_queries)

    queries = []
    queries.extend(manual_queries)
    queries.extend(base_terms)

    for base, seniority in product(base_terms, seniority_terms):
        queries.append(f"{base} {seniority}")

    for base, mode in product(base_terms, work_modes):
        queries.append(f"{base} {mode}")

    for base, seniority, mode in product(base_terms, seniority_terms, work_modes):
        queries.append(f"{base} {seniority} {mode}")

    for company in companies:
        queries.append(company)
        for base in base_terms:
            queries.append(f"{base} {company}")
        for base, seniority in product(base_terms, seniority_terms):
            queries.append(f"{base} {seniority} {company}")

    return _dedupe(queries)[:max_queries]
