#!/usr/bin/env python3
"""Bake DUN (state-assembly) results -> results-dun.json, keyed by code_state_dun.

Source: github.com/Thevesh/analysis-election-msia (peer-reviewed, cleaned).
  • candidates_prn15.csv  every state-election candidate: state, parlimen, dun,
                          name, party, acronym, votes, votes_perc, result

Coverage: Thevesh's `candidates_prn15.csv` is the **2023 six-state PRN**
(Selangor, Kelantan, Pulau Pinang, Kedah, Negeri Sembilan, Terengganu) — 245 of
the 600 DUN seats. The other DUN states held their assembly elections on other
dates and are NOT in that file, so we bake them from the Malaysian Election
Corpus (github.com/Thevesh/paper-meco-results, peer-reviewed) below — each state's
MOST RECENT state general election, plus any by-election won since (the true
current assemblyman). Johor is loaded from Bernama's official 2026 result page,
which attributes its figures to SPR.

  Baked from MECO: Sabah (2025), Sarawak (2021), Melaka (2021),
  Perak/Pahang/Perlis (2022) — the remaining ~299 seats, so results-dun.json now
  covers ~544 of 600. Johor's 56 official 2026 results are then loaded from the
  normalized Bernama/SPR snapshot produced by pipeline/johor_results.py, and
  Negeri Sembilan's 36 seats are finally replaced with the official PRN 2026
  results from pipeline/n9_results.py (overriding its 2023 six-state PRN rows).

    python3 pipeline/03_results_dun.py

Output public/data/results-dun.json:
  { "10_N.01": {state,name,party,party_full,coalition,coalition_full,votes,
                vote_pct,majority,majority_pct,turnout,n_candidates,
                runner_up:{name,party,votes}}, ... }
  (keyed on seats-dun.json `code` = "{state_code}_{dun_code}"; turnout is null
   where the older source lacks registered-voter counts; Johor has official %.)
"""
import csv
import json
import os
import urllib.request

from johor_results import SNAPSHOT as JOHOR_SNAPSHOT
from johor_results import results_rows_from_snapshot, validate_snapshot
import n9_results

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "..", "public", "data")
BASE = "https://raw.githubusercontent.com/Thevesh/analysis-election-msia/main/data"
FILES = {"candidates_prn15.csv": f"{BASE}/candidates_prn15.csv"}

# Same coalition normalisation as 02_results.py: PRN ballots label PAS, DAP etc.
# at component-party level — fold them to the winning bloc for the choropleth,
# while the detail panel still shows the component `party`.
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


def load(fn):
    path = os.path.join(RAW, fn)
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        urllib.request.urlretrieve(FILES[fn], path)
    with open(path) as f:
        return list(csv.DictReader(f))


def dun_code(dun):
    # "N.01 Ayer Hangat" -> "N.01"
    return dun.split(" ", 1)[0]


# ---------------------------------------------------------------------------
# Other DUN states — Malaysian Election Corpus (MECO), Thevesh/paper-meco-results
# ---------------------------------------------------------------------------
# consol_ballots.csv is a single coalition-resolved ballot file spanning EVERY
# Malaysian election, so we bake each remaining state's most recent state general
# election from it, then overlay any post-election by-election (current holder).
MECO_BALLOTS = "https://raw.githubusercontent.com/Thevesh/paper-meco-results/main/data/consol_ballots.csv"
MECO_PARTY = "https://raw.githubusercontent.com/Thevesh/paper-meco-results/main/data/lookup_party.csv"

# state -> (MECO election label, display label). MOST RECENT state general election
# as of 2026-07: Sabah went again in Nov 2025 (SE-15), so its 2020 assembly is stale.
MECO_TARGETS = {
    "Sabah":   ("SE-15", "Sabah 2025"),
    "Sarawak": ("SE-12", "Sarawak 2021"),
    "Melaka":  ("SE-15", "Melaka 2021"),
    "Pahang":  ("SE-15", "Pahang 2022"),
    "Perak":   ("SE-15", "Perak 2022"),
    "Perlis":  ("SE-15", "Perlis 2022"),
}
# seats whose sitting rep changed at a by-election AFTER that state's general
# election get overlaid in apply_byelection_overlays() below — date-driven from
# MECO's BY-ELECTION rows (no curated seat list to fall out of date).

MECO_COAL_FULL = {
    "BN": "Barisan Nasional", "PH": "Pakatan Harapan", "PN": "Perikatan Nasional",
    "GPS": "Gabungan Parti Sarawak", "GRS": "Gabungan Rakyat Sabah", "WARISAN": "Warisan",
    "KDM": "Parti Kesejahteraan Demokratik Masyarakat", "PSB": "Parti Sarawak Bersatu",
    "UPKO": "United Progressive Kinabalu Organisation", "STAR": "Homeland Solidarity Party (STAR)",
    "BEBAS": "Bebas (Independent)",
}


def _meco_load(url, fn):
    path = os.path.join(RAW, fn)
    if not os.path.exists(path):
        os.makedirs(RAW, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    with open(path) as f:
        return list(csv.DictReader(f))


def _vint(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def _meco_bloc(party, coalition):
    # MECO tags solo runners / independents with coalition 'ALONE' — surface the party
    # itself as the bloc (WARISAN, PSB, STAR, KDM, BEBAS …) so the choropleth + pill
    # show something meaningful instead of the null sentinel.
    return party if coalition in ("ALONE", "BEBAS", "") else coalition


def _meco_entry(ballots, party_full, election_display):
    lst = sorted(ballots, key=lambda b: _vint(b["votes"]), reverse=True)
    win = next((b for b in lst if b["result"].strip().lower() in ("won", "won_uncontested")), lst[0])
    runner = next((b for b in lst if b is not win), None)
    total = sum(_vint(b["votes"]) for b in lst)
    wv = _vint(win["votes"])
    contested = len(lst) > 1 and total > 0
    bloc = _meco_bloc(win["party"], win["coalition"])
    majority = (wv - _vint(runner["votes"])) if (runner and contested) else None
    entry = {
        "state": win["state"],
        "name": win["name"],
        "party": win["party"],
        "party_full": party_full.get(win["party"], win["party"]),
        "coalition": bloc,
        "coalition_full": MECO_COAL_FULL.get(bloc, party_full.get(bloc, bloc)),
        "votes": wv,
        "vote_pct": round(100 * wv / total, 1) if total else None,
        "majority": majority,
        "majority_pct": round(100 * majority / total, 1) if (majority is not None and total) else None,
        "turnout": None,  # registered-voter counts aren't in consol_ballots
        "n_candidates": len(lst),
        "election": election_display,
    }
    if runner and contested:
        entry["runner_up"] = {"name": runner["name"], "party": runner["party"], "votes": _vint(runner["votes"])}
    return entry


def build_meco_states(valid, st2code):
    """Return {seat_code: entry} for the non-PRN23 DUN states, from MECO."""
    ballots = _meco_load(MECO_BALLOTS, "meco_consol_ballots.csv")
    plook = {r["party"]: r["party_name_en"] for r in _meco_load(MECO_PARTY, "meco_lookup_party.csv")}
    out, added, overlaid, unmatched = {}, {}, [], []
    for state, (elabel, edisp) in MECO_TARGETS.items():
        sc = st2code[state]
        by_seat = {}
        for b in ballots:
            if b["state"] == state and b["election"] == elabel and dun_code(b["seat"]).startswith("N."):
                by_seat.setdefault(dun_code(b["seat"]), []).append(b)
        for ncode, lst in by_seat.items():
            key = f"{sc}_{ncode}"
            if key not in valid:
                unmatched.append(key)
                continue
            out[key] = _meco_entry(lst, plook, edisp)
        added[state] = len([k for k in by_seat if f"{sc}_{k}" in valid])
    return out, added, unmatched


def _normname(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def apply_byelection_overlays(out, st2code, seat_names):
    """Overlay every DUN by-election dated AFTER that state's baked general
    election — the true current holder supersedes the general result. Date-driven
    from MECO's BY-ELECTION rows, so new by-elections land on a simple re-run.
    (Johor never enters `out` — its sitting reps come from prn16-johor.json —
    so Johor by-elections are skipped by the `key in out` gate.)"""
    ballots = _meco_load(MECO_BALLOTS, "meco_consol_ballots.csv")
    plook = {r["party"]: r["party_name_en"] for r in _meco_load(MECO_PARTY, "meco_lookup_party.csv")}
    # the baked general election's polling day per state: MECO_TARGETS states use
    # their bake label; the PRN-2023 six default to their own SE-15 (Aug 2023)
    baked = {}
    for state in st2code:
        elabel = MECO_TARGETS.get(state, (None,))[0] or "SE-15"
        dates = [b["date"] for b in ballots if b["state"] == state and b["election"] == elabel]
        if dates:
            baked[state] = max(dates)
    by_seat = {}
    for b in ballots:
        if b["election"] != "BY-ELECTION" or not dun_code(b["seat"]).startswith("N."):
            continue
        if b["state"] not in st2code:
            continue
        by_seat.setdefault((b["state"], dun_code(b["seat"])), []).append(b)
    overlaid = []
    for (state, ncode), rows in by_seat.items():
        key = f"{st2code[state]}_{ncode}"
        latest = max(r["date"] for r in rows)
        if key not in out or latest <= baked.get(state, "9999"):
            continue
        lst = [r for r in rows if r["date"] == latest]
        # numbering-drift guard: the MECO seat name must match our boundary seat
        meco_name = _normname(lst[0]["seat"].split(" ", 1)[1]) if " " in lst[0]["seat"] else ""
        ours = _normname(seat_names.get(key, ""))
        if meco_name and ours and meco_name != ours:
            print(f"  ⚠ by-election seat-name mismatch for {key}: MECO '{lst[0]['seat']}' vs ours '{seat_names.get(key)}' — skipped")
            continue
        entry = _meco_entry(lst, plook, f"{state} {ncode} by-election {latest[:4]}")
        entry["_byelection"] = True
        out[key] = entry
        overlaid.append(f"{key} {latest} → {entry['name']} ({entry['coalition']})")
    return overlaid


def main():
    cands = load("candidates_prn15.csv")

    # state name -> state_code, taken from the SAME seats-dun.json the app joins on,
    # so every key here lines up with a real boundary seat (the universal join key).
    seats = json.load(open(os.path.join(OUT, "seats-dun.json")))["seats"]
    st2code = {s["state"]: s["state_code"] for s in seats}
    valid = {s["code"] for s in seats}

    by_seat = {}
    for c in cands:
        sc = st2code.get(c["state"])
        if sc is None:
            continue
        key = f"{sc}_{dun_code(c['dun'])}"
        by_seat.setdefault(key, []).append(c)

    out = {}
    skipped = []
    for code, lst in by_seat.items():
        if code not in valid:
            skipped.append(code)
            continue
        lst.sort(key=lambda c: int(c["votes"] or 0), reverse=True)
        total = sum(int(c["votes"] or 0) for c in lst)
        win = next((c for c in lst if c["result"].strip().lower() in ("won", "won_uncontested")), lst[0])
        runner = next((c for c in lst if c is not win), None)
        short = win["acronym"].strip()
        bloc, bloc_full = to_coalition(short)
        # coalition-level label (BN/PH/PN) → clean coalition name; component party
        # (PAS, DAP, …) keeps its own full name from the ballot.
        full = bloc_full if short == bloc else win["party"].title()
        majority = int(win["votes"] or 0) - (int(runner["votes"] or 0) if runner else 0)
        entry = {
            "state": win["state"],
            "name": win["name"],
            "party": short,
            "party_full": full,
            "coalition": bloc,
            "coalition_full": bloc_full,
            "votes": int(win["votes"] or 0),
            "vote_pct": round(100 * int(win["votes"] or 0) / total, 1) if total else None,
            "majority": majority,
            "majority_pct": round(100 * majority / total, 1) if total else None,
            "turnout": None,  # PRN registered-voter counts aren't in candidates_prn15.csv
            "n_candidates": len(lst),
        }
        if runner:
            entry["runner_up"] = {"name": runner["name"], "party": runner["acronym"].strip(),
                                  "votes": int(runner["votes"] or 0)}
        out[code] = entry

    prn23 = len(out)

    # add the remaining DUN states from the Malaysian Election Corpus
    meco, added, unmatched = build_meco_states(valid, st2code)
    out.update(meco)

    # by-election overlays — who holds each seat NOW (all DUN states, date-driven)
    seat_names = {s["code"]: s["name"] for s in seats}
    overlaid = apply_byelection_overlays(out, st2code, seat_names)

    # Official PRN Johor 2026 result (Bernama page, explicitly sourced to SPR).
    # Keep the normalized snapshot in git so an offline rebuild cannot silently
    # fall back to the dissolved 2022 assembly or election-night placeholders.
    johor_snapshot = json.load(open(JOHOR_SNAPSHOT))
    prn16 = json.load(open(os.path.join(OUT, "prn16-johor.json")))
    validate_snapshot(johor_snapshot, prn16)
    johor = results_rows_from_snapshot(johor_snapshot)
    out.update(johor)

    # Official PRN Negeri Sembilan 2026 result (same Bernama/SPR doctrine as
    # Johor): replace the dissolved 2023 rows baked above with the committed
    # normalized snapshot so an offline rebuild cannot silently regress.
    n9_snapshot = json.load(open(n9_results.SNAPSHOT))
    n9_results.validate_snapshot(n9_snapshot)
    n9 = n9_results.results_rows_from_snapshot(n9_snapshot)
    out.update(n9)

    path = os.path.join(OUT, "results-dun.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    from collections import Counter
    dist = Counter(v["coalition"] for v in out.values())
    states = Counter(v["state"] for v in out.values())
    print(f"  → results-dun.json  ({len(out)} of 600 DUN seats, {os.path.getsize(path)/1024:.0f} KB)")
    print(f"  PRN-2023 six-state: {prn23} seats | MECO other states: {len(meco)} seats | "
          f"Johor 2026: {len(johor)} seats | N9 2026: {len(n9)} seats")
    print(f"  MECO states: " + ", ".join(f"{s} {n}" for s, n in added.items()))
    print(f"  by-election overlays (current holder): {len(overlaid)}")
    for o in overlaid:
        print(f"    · {o}")
    print(f"  states covered ({len(states)}): " + ", ".join(f"{s} {n}" for s, n in states.most_common()))
    print("  seats won by coalition: " + ", ".join(f"{p} {n}" for p, n in dist.most_common()))
    if skipped:
        print(f"  ⚠ {len(skipped)} PRN seats had no matching boundary code (skipped): {skipped[:5]}")
    if unmatched:
        print(f"  ⚠ {len(unmatched)} MECO seats had no matching boundary code (skipped): {unmatched[:5]}")


if __name__ == "__main__":
    print("Baking DUN (PRN) state-assembly results…")
    main()
    print("Done.")
