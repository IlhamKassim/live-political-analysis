#!/usr/bin/env python3
"""Bake per-state context: head of government + election clock (+ economy when added).

Sources (curated, verified 2026-07-04 via web research — see AGENT_LOG):
  • MB/KM/Premier per state incl. the Dec-2025 Perlis change and Sabah's Nov-2025
    re-mandate; caretakers flagged for the dissolved assemblies (Johor, N9).
  • Election clock per legislature: last election, first sitting (starts the 5-year
    constitutional term), auto-dissolution date, and officially announced elections.

Output: public/data/state-context.json keyed by our canonical state names.
"""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "public", "data", "state-context.json")
SEATS = os.path.join(ROOT, "public", "data", "seats-parlimen.json")

MB = {
    "Johor":           {"name": "Onn Hafiz Ghazi", "title": "MB", "party": "UMNO", "coalition": "BN", "since": "2022", "caretaker": True},
    "Kedah":           {"name": "Muhammad Sanusi Md Nor", "title": "MB", "party": "PAS", "coalition": "PN", "since": "2020", "caretaker": False},
    "Kelantan":        {"name": "Mohd Nassuruddin Daud", "title": "MB", "party": "PAS", "coalition": "PN", "since": "2023", "caretaker": False},
    "Melaka":          {"name": "Ab Rauf Yusoh", "title": "KM", "party": "UMNO", "coalition": "BN", "since": "2023", "caretaker": False},
    "Negeri Sembilan": {"name": "Aminuddin Harun", "title": "MB", "party": "PKR", "coalition": "PH", "since": "2018", "caretaker": True},
    "Pahang":          {"name": "Wan Rosdy Wan Ismail", "title": "MB", "party": "UMNO", "coalition": "BN", "since": "2018", "caretaker": False},
    "Perak":           {"name": "Saarani Mohamad", "title": "MB", "party": "UMNO", "coalition": "BN", "since": "2020", "caretaker": False},
    "Perlis":          {"name": "Abu Bakar Hamzah", "title": "MB", "party": "BERSATU", "coalition": "PN", "since": "2025", "caretaker": False},
    "Pulau Pinang":    {"name": "Chow Kon Yeow", "title": "KM", "party": "DAP", "coalition": "PH", "since": "2018", "caretaker": False},
    "Sabah":           {"name": "Hajiji Noor", "title": "KM", "party": "GAGASAN", "coalition": "GRS", "since": "2020", "caretaker": False},
    "Sarawak":         {"name": "Abang Johari Openg", "title": "Premier", "party": "PBB", "coalition": "GPS", "since": "2017", "caretaker": False},
    "Selangor":        {"name": "Amirudin Shari", "title": "MB", "party": "PKR", "coalition": "PH", "since": "2018", "caretaker": False},
    "Terengganu":      {"name": "Ahmad Samsuri Mokhtar", "title": "MB", "party": "PAS", "coalition": "PN", "since": "2018", "caretaker": False},
}

# last_election, first_sitting -> dissolve_by = first_sitting + 5y (verified vs press);
# next_election only when officially announced by the EC.
CLOCK = {
    "parlimen":        {"last": "2022-11-19", "sat": "2022-12-19", "dissolve_by": "2027-12-19", "next": None},
    "Johor":           {"last": "2022-03-12", "sat": "2022-04-21", "dissolve_by": None, "next": "2026-07-11"},
    "Kedah":           {"last": "2023-08-12", "sat": "2023-09-25", "dissolve_by": "2028-09-25", "next": None},
    "Kelantan":        {"last": "2023-08-12", "sat": "2023-09-05", "dissolve_by": "2028-09-05", "next": None},
    "Melaka":          {"last": "2021-11-20", "sat": "2021-12-27", "dissolve_by": "2026-12-27", "next": None},
    "Negeri Sembilan": {"last": "2023-08-12", "sat": "2023-09-26", "dissolve_by": None, "next": "2026-08-01"},
    "Pahang":          {"last": "2022-11-19", "sat": "2022-12-29", "dissolve_by": "2027-12-29", "next": None},
    "Perak":           {"last": "2022-11-19", "sat": "2022-12-19", "dissolve_by": "2027-12-19", "next": None},
    "Perlis":          {"last": "2022-11-19", "sat": "2022-12-19", "dissolve_by": "2027-12-19", "next": None},
    "Pulau Pinang":    {"last": "2023-08-12", "sat": "2023-08-29", "dissolve_by": "2028-08-29", "next": None},
    "Sabah":           {"last": "2025-11-29", "sat": "2025-12-11", "dissolve_by": "2030-12-11", "next": None},
    "Sarawak":         {"last": "2021-12-18", "sat": "2022-02-14", "dissolve_by": "2027-02-14", "next": None, "expected": "2026"},
    "Selangor":        {"last": "2023-08-12", "sat": "2023-09-19", "dissolve_by": "2028-09-19", "next": None},
    "Terengganu":      {"last": "2023-08-12", "sat": "2023-09-24", "dissolve_by": "2028-09-24", "next": None},
}

FT = ("W.P. Kuala Lumpur", "W.P. Putrajaya", "W.P. Labuan")


def main():
    with open(SEATS) as f:
        seats = json.load(f)["seats"]
    states = sorted({s["state"] for s in seats})
    out = {"checked": "2026-07-04", "parlimen": CLOCK["parlimen"], "states": {}}
    for st in states:
        entry = {}
        if st in MB:
            entry["gov"] = MB[st]
        clock = CLOCK.get(st)
        if st in FT:
            entry["clock"] = {"federal": True}   # FTs have no assembly — Parliament clock applies
        elif clock:
            entry["clock"] = clock
            # sanity: dissolve_by must equal first sitting + 5 years when set
            if clock.get("dissolve_by") and clock.get("sat"):
                sat = dt.date.fromisoformat(clock["sat"])
                exp = sat.replace(year=sat.year + 5)
                assert clock["dissolve_by"] == exp.isoformat(), f"{st}: clock mismatch"
        out["states"][st] = entry
    missing = [s for s in states if s not in MB and s not in FT]
    assert not missing, f"states without MB entry: {missing}"
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"state context: {len(out['states'])} states -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
