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
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "pipeline", "prn16_johor_candidates.csv")
SEATS_DUN = os.path.join(ROOT, "public", "data", "seats-dun.json")
OUT = os.path.join(ROOT, "public", "data", "prn16-johor.json")
# Malaysian Election Corpus ballots (cached by 03_results_dun.py) — used to add the
# CURRENT seat-holder's actual vote count, i.e. the winner of the most recent COMPLETED
# Johor election (the 2022 SE-15 poll, or a later by-election that superseded it).
MECO_BALLOTS = os.path.join(ROOT, "pipeline", "raw", "meco_consol_ballots.csv")

_TITLES = {"datuk", "dato", "datin", "dr", "haji", "hj", "tuan", "puan", "ir",
           "ts", "tan", "sri", "seri", "yb", "prof", "hajah", "ustaz"}


def _namekey(s):
    """Person-name key: drop titles / bin / binti / a-l / a-p / anak and punctuation."""
    toks = [t for t in re.split(r"[^a-z]+", (s or "").lower()) if t]
    return "".join(t for t in toks if t not in _TITLES and t not in ("bin", "binti", "al", "ap", "anak"))


def enrich_incumbent_votes(seats):
    """Add incumbent_votes_2022 + incumbent_pct_2022 = the CURRENT holder's votes,
    from the most recent completed Johor election (SE-15 2022 or a later by-election).
    Excludes SE-16 (the 2026 poll being held now — no results yet)."""
    if not os.path.exists(MECO_BALLOTS):
        print("  (skip incumbent votes: MECO ballots not cached — run 03_results_dun.py first)")
        return
    by_seat = {}
    with open(MECO_BALLOTS) as f:
        for r in csv.DictReader(f):
            if r["state"] != "Johor":
                continue
            nc = r["seat"].split(" ", 1)[0]
            if not nc.startswith("N."):
                continue
            # only COMPLETED contests: the 2022 general poll + post-2022 by-elections
            if r["election"] == "SE-15" or (r["election"] == "BY-ELECTION" and "2022-03-12" < r["date"] < "2026-01-01"):
                by_seat.setdefault(nc, []).append(r)
    added, warn = 0, []
    for code, s in seats.items():
        rows = by_seat.get(s["ncode"], [])
        if not rows:
            continue
        latest = max(r["date"] for r in rows)
        contest = sorted((r for r in rows if r["date"] == latest),
                         key=lambda r: int(float(r["votes"] or 0)), reverse=True)
        win = next((r for r in contest if r["result"].strip().lower() in ("won", "won_uncontested")), contest[0])
        try:
            v = int(float(win["votes"] or 0))
        except ValueError:
            v = 0
        if v <= 0:
            continue
        s["incumbent_votes_2022"] = v
        try:
            pct = round(float(win["votes_perc"] or 0), 1)
            if pct:
                s["incumbent_pct_2022"] = pct
        except ValueError:
            pass
        # the full last contest (top 3) → "how this seat voted last time" recap
        total = sum(int(float(r["votes"] or 0)) for r in contest)
        field = []
        for r in contest[:3]:
            rv = int(float(r["votes"] or 0))
            coal = r["coalition"] if r["coalition"] not in ("ALONE", "BEBAS", "") else r["party"]
            field.append({
                "name": r["name"], "party": r["party"], "coalition": coal, "votes": rv,
                "pct": round(100 * rv / total, 1) if total else None,
            })
        if field:
            s["last_field"] = field
            s["last_field_year"] = latest[:4]
        added += 1
        # cross-check the MECO winner against the curated incumbent name (same person expected)
        if s.get("incumbent_2022") and _namekey(win["name"]) != _namekey(s["incumbent_2022"]):
            nk_w, nk_i = _namekey(win["name"]), _namekey(s["incumbent_2022"])
            if not (nk_w in nk_i or nk_i in nk_w):
                warn.append(f"{code} {s['ncode']}: curated '{s['incumbent_2022']}' vs MECO winner '{win['name']}' ({latest})")
    print(f"  incumbent votes enriched: {added}/{len(seats)}")
    for w in warn:
        print(f"    ⚠ name check: {w}")

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

    enrich_incumbent_votes(seats)

    out = {"election": ELECTION, "contested": dict(contested), "seats": seats}
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"PRN16 Johor: {len(seats)} seats, {total} candidates -> {os.path.relpath(OUT, ROOT)}")
    print(f"  contested-by: {dict(contested.most_common())}")


if __name__ == "__main__":
    main()
