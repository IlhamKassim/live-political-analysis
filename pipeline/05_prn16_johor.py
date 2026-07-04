#!/usr/bin/env python3
"""Bake the PRN16 Johor (2026 state election) live-election dataset.

Source of truth: pipeline/prn16_johor_candidates.csv — the SPR-confirmed
nomination list, triple-cross-checked on 2026-07-04 against:
  • Sinar Harian's full published list (172 candidates, SPR-confirmed);
  • Wikipedia BM candidates table (independently sums to the official totals);
  • Wikipedia EN candidates table (partial; used as tie-breaker).
Adjudications recorded in AGENT_LOG.md. Official shape asserted below:
56 seats, 172 candidates, contest breakdown 14×2-way / 27×3-way / 12×4-way /
3×5-way (SPR announcement).

Output: public/data/prn16-johor.json
"""
import csv
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "pipeline", "prn16_johor_candidates.csv")
SEATS_DUN = os.path.join(ROOT, "public", "data", "seats-dun.json")
OUT = os.path.join(ROOT, "public", "data", "prn16-johor.json")

ELECTION = {
    "id": "prn16-johor",
    "name": "PRN Johor 2026",
    "name_ms": "PRN Johor 2026",
    "state": "Johor",
    "tier": "dun",
    "nomination_day": "2026-06-27",
    "early_voting": "2026-07-07",
    "polling_day": "2026-07-11",
    "total_seats": 56,
    "majority": 29,
    "phase": "campaign",   # campaign | live | final — live phase served via /api/live/johor
    "source": "SPR-confirmed nomination lists (Sinar Harian + Wikipedia BM/EN), cross-checked 2026-07-04",
    "check_voter_url": "https://mysprsemak.spr.gov.my/",
}


def main():
    with open(SEATS_DUN) as f:
        dun = json.load(f)
    dun_seats = dun["seats"] if isinstance(dun, dict) else dun
    canon = {s["code"]: s["name"] for s in dun_seats if s.get("state") == "Johor"}
    assert len(canon) == 56, f"expected 56 Johor DUN seats, got {len(canon)}"

    seats = {}
    with open(CSV, newline="") as f:
        for row in csv.DictReader(f):
            code = row["code"]
            assert code in canon, f"unknown seat code {code}"
            s = seats.setdefault(code, {
                "ncode": row["ncode"],
                "name": canon[code],
                "electorate": int(row["electorate"]) if row["electorate"] else None,
                "incumbent_2022": row["incumbent_2022"] or None,
                "incumbent_party_2022": row["incumbent_party_2022"] or None,
                "majority_2022": row["majority_2022"] or None,
                "candidates": [],
            })
            cand = {
                "name": row["candidate"],
                "coalition": row["coalition"],
                "party": row["party"],
            }
            if row["symbol"]:
                cand["symbol"] = row["symbol"]
            if row["ballot_name"]:
                cand["ballot_name"] = row["ballot_name"]
            s["candidates"].append(cand)

    total = sum(len(s["candidates"]) for s in seats.values())
    ways = Counter(len(s["candidates"]) for s in seats.values())
    assert len(seats) == 56, f"expected 56 seats with candidates, got {len(seats)}"
    assert total == 172, f"expected 172 candidates (SPR official), got {total}"
    assert dict(ways) == {2: 14, 3: 27, 4: 12, 5: 3}, f"contest breakdown mismatch: {dict(ways)}"
    for code, s in seats.items():
        coals = [c["coalition"] for c in s["candidates"]]
        assert len(coals) >= 2, f"{code}: fewer than 2 candidates"

    # contested-by tally for the campaign card (seats each coalition is fielding in)
    contested = Counter()
    for s in seats.values():
        for c in s["candidates"]:
            contested[c["coalition"]] += 1

    out = {"election": ELECTION, "contested": dict(contested), "seats": seats}
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"PRN16 Johor: {len(seats)} seats, {total} candidates -> {os.path.relpath(OUT, ROOT)}")
    print(f"  contested-by: {dict(contested.most_common())}")


if __name__ == "__main__":
    main()
