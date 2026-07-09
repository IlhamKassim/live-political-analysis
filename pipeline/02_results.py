#!/usr/bin/env python3
"""Bake GE15 (PRU15) parliament results -> results-ge15.json, keyed by code_parlimen.

Source: github.com/Thevesh/analysis-election-msia (peer-reviewed, cleaned).
  • candidates_ge15.csv     every candidate: name, party(coalition), votes, won flag
  • results_parlimen_ge15.csv  per-seat: majority, turnout

    python3 pipeline/02_results.py

Output public/data/results-ge15.json:
  { "P.001": {state,name,party,party_full,votes,vote_pct,majority,majority_pct,
              turnout,n_candidates,runner_up:{name,party,votes}}, ... }
"""
import csv
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "..", "public", "data")
BASE = "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data"
FILES = {"candidates_ge15.csv": f"{BASE}/candidates_ge15.csv",
         "results_parlimen_ge15.csv": f"{BASE}/results_parlimen_ge15.csv"}


def load(fn):
    path = os.path.join(RAW, fn)
    if not os.path.exists(path):
        urllib.request.urlretrieve(FILES[fn], path)
    with open(path) as f:
        return list(csv.DictReader(f))


def code_of(parlimen):
    # "P.001 Padang Besar" -> "P.001"
    return parlimen.split(" ", 1)[0]


def party_short(party):
    # "PERIKATAN NASIONAL (PN)" -> ("PN", "Perikatan Nasional")
    m = re.search(r"\(([^)]+)\)\s*$", party)
    short = m.group(1) if m else party
    full = re.sub(r"\s*\([^)]+\)\s*$", "", party).title()
    return short, full


# GE15 ballots mixed coalition labels (PH/PN/BN) with a few component-party
# labels (DAP, MUDA, PAS). Normalise to the winning bloc so the choropleth
# groups correctly; the component `party` is still kept for the detail panel.
COALITION = {
    "DAP": "PH", "PKR": "PH", "AMANAH": "PH", "MUDA": "PH", "UPKO": "PH",
    "PAS": "PN", "BERSATU": "PN", "GERAKAN": "PN",
    "UMNO": "BN", "MCA": "BN", "MIC": "BN",
    "PBB": "GPS", "SUPP": "GPS", "PRS": "GPS", "PDP": "GPS",
}
COALITION_FULL = {
    "PH": "Pakatan Harapan", "PN": "Perikatan Nasional", "BN": "Barisan Nasional",
    "GPS": "Gabungan Parti Sarawak", "GRS": "Gabungan Rakyat Sabah",
    "WARISAN": "Warisan", "KDM": "KDM", "PBM": "Parti Bangsa Malaysia",
    "BEBAS": "Bebas",
}


def to_coalition(short):
    bloc = COALITION.get(short, short)
    return bloc, COALITION_FULL.get(bloc, bloc.title())


# ---------------------------------------------------------------------------
# By-election overlays — the true current holder supersedes the GE15 winner
# (same doctrine as 03_results_dun.py). MECO (Thevesh/paper-meco-results)
# consol_ballots.csv lists every Malaysian by-election; any parliament (P.xxx)
# by-election dated after GE15 polling day overlays that seat, date-driven so
# future by-elections land on a simple re-run instead of a curated list.
# The row keeps `election` + `_byelection` so the card cites the right poll.
# ---------------------------------------------------------------------------
GE15_POLLING_DAY = "2022-11-19"
MECO_BASE = "https://raw.githubusercontent.com/Thevesh/paper-meco-results/main/data"
MECO_FILES = {"meco_consol_ballots.csv": f"{MECO_BASE}/consol_ballots.csv",
              "meco_lookup_party.csv": f"{MECO_BASE}/lookup_party.csv"}


def _meco_load(fn):
    path = os.path.join(RAW, fn)
    if not os.path.exists(path):
        urllib.request.urlretrieve(MECO_FILES[fn], path)
    with open(path) as f:
        return list(csv.DictReader(f))


def _vint(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def apply_byelection_overlays(out):
    ballots = _meco_load("meco_consol_ballots.csv")
    plook = {r["party"]: r["party_name_en"] for r in _meco_load("meco_lookup_party.csv")}
    by_seat = {}
    for b in ballots:
        if b["election"] != "BY-ELECTION" or not b["seat"].startswith("P."):
            continue
        if b["date"] <= GE15_POLLING_DAY:
            continue
        by_seat.setdefault(code_of(b["seat"]), []).append(b)
    overlaid = []
    for code, rows in by_seat.items():
        if code not in out:
            continue
        latest = max(r["date"] for r in rows)
        lst = sorted((r for r in rows if r["date"] == latest),
                     key=lambda b: _vint(b["votes"]), reverse=True)
        win = next((b for b in lst if b["result"].strip().lower() in ("won", "won_uncontested")), lst[0])
        runner = next((b for b in lst if b is not win), None)
        total = sum(_vint(b["votes"]) for b in lst)
        wv = _vint(win["votes"])
        # MECO tags independents/solo runners with coalition 'ALONE' — surface the party
        party = win["party"]
        bloc = party if win["coalition"] in ("ALONE", "BEBAS", "") else win["coalition"]
        majority = (wv - _vint(runner["votes"])) if runner else None
        seat_name = win["seat"].split(" ", 1)[1] if " " in win["seat"] else win["seat"]
        entry = {
            "state": win["state"],
            "name": win["name"],
            "party": party,
            "party_full": plook.get(party, party),
            "coalition": bloc,
            "coalition_full": COALITION_FULL.get(bloc, plook.get(bloc, bloc)),
            "votes": wv,
            "vote_pct": round(100 * wv / total, 1) if total else None,
            "majority": majority,
            "majority_pct": round(100 * majority / total, 1) if (majority is not None and total) else None,
            "turnout": None,  # registered-voter counts aren't in consol_ballots
            "n_candidates": len(lst),
            "election": f"{seat_name} by-election {latest[:4]}",
            "_byelection": True,
        }
        if runner:
            entry["runner_up"] = {"name": runner["name"], "party": runner["party"], "votes": _vint(runner["votes"])}
        out[code] = entry
        overlaid.append(f"{code} {latest} → {entry['name']} ({entry['coalition']})")
    return overlaid


def main():
    cands = load("candidates_ge15.csv")
    results = {code_of(r["parlimen"]): r for r in load("results_parlimen_ge15.csv")}

    by_seat = {}
    for c in cands:
        by_seat.setdefault(code_of(c["parlimen"]), []).append(c)

    out = {}
    for code, lst in by_seat.items():
        lst.sort(key=lambda c: int(c["votes"]), reverse=True)
        total = sum(int(c["votes"]) for c in lst)
        win = next((c for c in lst if c["result"] == "1"), lst[0])
        runner = next((c for c in lst if c is not win), None)
        ws, wf = party_short(win["party"])
        bloc, bloc_full = to_coalition(ws)
        res = results.get(code, {})
        majority = int(res["majoriti"]) if res.get("majoriti") else int(win["votes"]) - (int(runner["votes"]) if runner else 0)
        entry = {
            "state": win["state"],
            "name": win["name"],
            "party": ws,
            "party_full": wf,
            "coalition": bloc,
            "coalition_full": bloc_full,
            "votes": int(win["votes"]),
            "vote_pct": round(100 * int(win["votes"]) / total, 1) if total else None,
            "majority": majority,
            "majority_pct": round(100 * majority / total, 1) if total else None,
            "turnout": round(float(res["peratus_keluar"]), 1) if res.get("peratus_keluar") else None,
            "n_candidates": len(lst),
        }
        if runner:
            rs, _ = party_short(runner["party"])
            entry["runner_up"] = {"name": runner["name"], "party": rs, "votes": int(runner["votes"])}
        out[code] = entry

    # by-election overlays — who holds the seat NOW
    overlaid = apply_byelection_overlays(out)

    path = os.path.join(OUT, "results-ge15.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    # report party distribution so we can sanity-check + design the palette
    from collections import Counter
    dist = Counter(v["coalition"] for v in out.values())
    print(f"  → results-ge15.json  ({len(out)} seats, {os.path.getsize(path)/1024:.0f} KB)")
    print(f"  by-election overlays (current holder): {len(overlaid)}")
    for o in overlaid:
        print(f"    · {o}")
    print("  seats won by coalition:")
    for p, n in dist.most_common():
        print(f"      {p:10s} {n}")


if __name__ == "__main__":
    print("Baking GE15 parliament results…")
    main()
    print("Done.")
