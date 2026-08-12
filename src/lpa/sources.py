"""Fetching public datasets. The only part of the Baseline Loader that is I/O.

GE15 results and the parliamentary census come from Thevesh Theva's Malaysian
election dataset, which publishes the Election Commission's candidate-level
results alongside DOSM census data keyed by parliamentary Seat. Free to fetch,
in line with the zero-cost constraint (ADR 0002).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

import httpx

ELECTION_DATA_BASE = "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data"
GE15_CANDIDATES_URL = f"{ELECTION_DATA_BASE}/candidates_ge15.csv"
PARLIAMENTARY_CENSUS_URL = f"{ELECTION_DATA_BASE}/census_parlimen.csv"


def fetch_csv(url: str, timeout: float = 60.0) -> list[dict[str, str]]:
    """Fetch a CSV over HTTP and return its rows as dicts."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return list(csv.DictReader(io.StringIO(response.text)))


def fetch_ge15_candidates() -> Sequence[dict[str, str]]:
    return fetch_csv(GE15_CANDIDATES_URL)


def fetch_parliamentary_census() -> Sequence[dict[str, str]]:
    return fetch_csv(PARLIAMENTARY_CENSUS_URL)
