#!/usr/bin/env python3
"""Bake DUN (state-assembly) results -> results-dun.json, keyed by code_state_dun.

Source: github.com/Thevesh/analysis-election-msia (peer-reviewed, cleaned).
  • candidates_prn15.csv  every state-election candidate: state, parlimen, dun,
                          name, party, acronym, votes, votes_perc, result

Coverage note: Thevesh's `candidates_prn15.csv` is the **2023 six-state PRN**
(Selangor, Kelantan, Pulau Pinang, Kedah, Negeri Sembilan, Terengganu) — 245 of
the 600 DUN seats. The other 7 DUN states held their state elections on other
dates (Sarawak '21, Sabah '20, Melaka '21, Johor '22, and Perlis/Perak/Pahang
concurrent with GE15 '22) and are NOT in this file, so their seats are simply
absent from the output. The frontend is per-seat data-driven: a DUN seat with no
entry keeps the existing "state-election results coming soon" note.

    python3 pipeline/03_results_dun.py

Output public/data/results-dun.json:
  { "10_N.01": {state,name,party,party_full,coalition,coalition_full,votes,
                vote_pct,majority,majority_pct,turnout,n_candidates,
                runner_up:{name,party,votes}}, ... }
  (keyed on seats-dun.json `code` = "{state_code}_{dun_code}"; turnout is null —
   PRN registered-voter counts aren't in this source.)
"""
import csv
import json
import os
import urllib.request

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

    path = os.path.join(OUT, "results-dun.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    from collections import Counter
    dist = Counter(v["coalition"] for v in out.values())
    states = Counter(v["state"] for v in out.values())
    print(f"  → results-dun.json  ({len(out)} of 600 DUN seats, {os.path.getsize(path)/1024:.0f} KB)")
    print(f"  states covered ({len(states)}): " + ", ".join(f"{s} {n}" for s, n in states.most_common()))
    print("  seats won by coalition: " + ", ".join(f"{p} {n}" for p, n in dist.most_common()))
    if skipped:
        print(f"  ⚠ {len(skipped)} seats had no matching boundary code (skipped): {skipped[:5]}")


if __name__ == "__main__":
    print("Baking DUN (PRN) state-assembly results…")
    main()
    print("Done.")
