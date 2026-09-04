#!/usr/bin/env python3
"""Bake verified constituency content for Phase 2 tabs.

This step intentionally only emits data with clear, repeatable provenance:
  • candidate rows from Thevesh / ElectionData.MY election CSVs already used by
    the result pipeline;
  • official SPR/MySPR links for voter lookup, candidates and results.

It does NOT invent bios, controversies, promises, performance scores, news, or
local issues. Those need their own sourced datasets before they appear in-app.

Outputs:
  public/data/candidates-ge15.json
  public/data/candidates-dun-prn15.json
  public/data/voting-guide.json
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
FILES = {
    "candidates_ge15.csv": f"{BASE}/candidates_ge15.csv",
    "candidates_prn15.csv": f"{BASE}/candidates_prn15.csv",
}

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


def load(fn):
    os.makedirs(RAW, exist_ok=True)
    path = os.path.join(RAW, fn)
    if not os.path.exists(path):
        urllib.request.urlretrieve(FILES[fn], path)
    with open(path) as f:
        return list(csv.DictReader(f))


def write_json(name, data):
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  → {name} ({len(data) if isinstance(data, dict) else 'ok'}, {os.path.getsize(path)/1024:.0f} KB)")


def code_of(parlimen):
    return parlimen.split(" ", 1)[0]


def dun_code(dun):
    return dun.split(" ", 1)[0]


def party_short(party):
    m = re.search(r"\(([^)]+)\)\s*$", party)
    short = m.group(1).strip() if m else party.strip()
    full = re.sub(r"\s*\([^)]+\)\s*$", "", party).strip().title()
    return short, full


def to_coalition(short):
    bloc = COALITION.get(short, short)
    return bloc, COALITION_FULL.get(bloc, bloc.title())


def to_int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def to_age(value):
    age = to_int(value)
    return age if age > 0 else None


def candidate_entry(row, *, rank, total_votes, party, party_full, coalition, coalition_full, result):
    votes = to_int(row.get("votes"))
    return {
        "rank": rank,
        "ballot_order": to_int(row.get("ballot_order") or row.get("ballot_order_y") or row.get("ballot_order_x")) or None,
        "name": row.get("name", "").strip(),
        "name_ballot": (row.get("name_display") or row.get("name_ballot") or row.get("name") or "").strip(),
        "party": party,
        "party_full": party_full,
        "coalition": coalition,
        "coalition_full": coalition_full,
        "votes": votes,
        "vote_pct": round(100 * votes / total_votes, 1) if total_votes else None,
        "result": result,
        "age": to_age(row.get("age")),
    }


def bake_ge15_candidates():
    by_seat = {}
    for row in load("candidates_ge15.csv"):
        by_seat.setdefault(code_of(row["parlimen"]), []).append(row)

    out = {}
    for code, rows in by_seat.items():
        rows.sort(key=lambda r: to_int(r.get("votes")), reverse=True)
        total = sum(to_int(r.get("votes")) for r in rows)
        candidates = []
        for rank, row in enumerate(rows, 1):
            short, full = party_short(row.get("party", ""))
            bloc, bloc_full = to_coalition(short)
            candidates.append(candidate_entry(
                row,
                rank=rank,
                total_votes=total,
                party=short,
                party_full=full,
                coalition=bloc,
                coalition_full=bloc_full,
                result="won" if row.get("result") == "1" else (row.get("result_desc") or "lost"),
            ))
        out[code] = {
            "election": "GE15 / PRU15",
            "source": "Thevesh / ElectionData.MY candidates_ge15.csv",
            "source_url": FILES["candidates_ge15.csv"],
            "candidates": candidates,
        }
    return out


def bake_prn15_candidates():
    seats = json.load(open(os.path.join(OUT, "seats-dun.json")))["seats"]
    st2code = {s["state"]: s["state_code"] for s in seats}
    valid = {s["code"] for s in seats}

    by_seat = {}
    for row in load("candidates_prn15.csv"):
        sc = st2code.get(row["state"])
        if sc is None:
            continue
        key = f"{sc}_{dun_code(row['dun'])}"
        if key in valid:
            by_seat.setdefault(key, []).append(row)

    out = {}
    for code, rows in by_seat.items():
        rows.sort(key=lambda r: to_int(r.get("votes")), reverse=True)
        total = sum(to_int(r.get("votes")) for r in rows)
        candidates = []
        for rank, row in enumerate(rows, 1):
            short = row.get("acronym", "").strip()
            bloc, bloc_full = to_coalition(short)
            full = bloc_full if short == bloc else row.get("party", "").strip().title()
            result = row.get("result", "").strip().lower() or "lost"
            candidates.append(candidate_entry(
                row,
                rank=rank,
                total_votes=total,
                party=short,
                party_full=full,
                coalition=bloc,
                coalition_full=bloc_full,
                result=result,
            ))
        out[code] = {
            "election": "PRN 2023",
            "source": "Thevesh / ElectionData.MY candidates_prn15.csv",
            "source_url": FILES["candidates_prn15.csv"],
            "coverage_note": "2023 six-state PRN only",
            "candidates": candidates,
        }
    return out


def voting_guide():
    return {
        "updated": "2026-06-30",
        "source": "Suruhanjaya Pilihan Raya Malaysia / MySPR Semak",
        "source_url": "https://mysprsemak.spr.gov.my/",
        "privacy_note": "MyPolitik does not collect IC, police or military service numbers. Use official MySPR Semak for voter-specific lookup.",
        "privacy_note_ms": "MyPolitik tidak mengumpul nombor IC, polis atau tentera. Gunakan MySPR Semak rasmi untuk semakan khusus pengundi.",
        "items": [
            {
                "title": "Check voter registration and polling details",
                "title_ms": "Semak daftar pemilih dan maklumat mengundi",
                "body": "Use the official MySPR Semak voter lookup to check registration and polling information.",
                "body_ms": "Gunakan semakan pengundi rasmi MySPR Semak untuk menyemak pendaftaran dan maklumat mengundi.",
                "url": "https://mysprsemak.spr.gov.my/semakan/daftarPemilih",
                "label": "Open MySPR voter check",
                "label_ms": "Buka semakan pengundi MySPR",
            },
            {
                "title": "Check official candidates and results",
                "title_ms": "Semak calon dan keputusan rasmi",
                "body": "MySPR Semak provides official candidate and election-result lookup pages.",
                "body_ms": "MySPR Semak menyediakan halaman semakan calon dan keputusan pilihan raya rasmi.",
                "url": "https://mysprsemak.spr.gov.my/",
                "label": "Open MySPR Semak",
                "label_ms": "Buka MySPR Semak",
            },
            {
                "title": "Questions or corrections",
                "title_ms": "Pertanyaan atau pembetulan",
                "body": "Use the SPR portal for official enquiries, complaints and current election notices.",
                "body_ms": "Gunakan portal SPR untuk pertanyaan rasmi, aduan dan notis pilihan raya semasa.",
                "url": "https://www.spr.gov.my/",
                "label": "Open SPR portal",
                "label_ms": "Buka portal SPR",
            },
        ],
    }


def main():
    write_json("candidates-ge15.json", bake_ge15_candidates())
    prn15 = bake_prn15_candidates()
    # Negeri Sembilan's official PRN 2026 field replaces its dissolved 2023 rows
    # (same rebuild-preservation doctrine as 03_results_dun.py's result layers).
    import n9_results
    n9_snapshot = json.load(open(n9_results.SNAPSHOT))
    n9_results.validate_snapshot(n9_snapshot)
    prn15.update(n9_results.candidates_entries_from_snapshot(n9_snapshot))
    write_json("candidates-dun-prn15.json", prn15)
    write_json("voting-guide.json", voting_guide())


if __name__ == "__main__":
    print("Baking verified constituency content…")
    main()
    print("Done.")
