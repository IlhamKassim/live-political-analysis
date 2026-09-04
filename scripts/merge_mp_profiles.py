"""One-off join: `data/mp_profiles.json` x `frontend/public/data/politicians.json`.

Step 2 of the PolitikKu x mypolitik merge (see the plan at
`docs/design/ui-ux-brief.md`'s sibling merge notes, and the session that
produced this script). The two datasets were built independently and cover
different ground for the same 222 Seats, keyed on the same `P.xxx`
`code_parlimen`:

- `data/mp_profiles.json` (`scripts/build_mp_profiles.py`, ADR 0009) is a
  legislative/constituent-service profile: GE15 result, contact details,
  Divisions, sponsored Bills, and an explicit `unverified` block for
  anything Parliament's own sources don't establish. Only 199 of 222 Seats
  are profiled — a Seat this pipeline cannot honestly profile is recorded
  in `_skipped` with why, never guessed at.
- `frontend/public/data/politicians.json` (`frontend/pipeline/09_politicians.py`)
  is a bio/media profile: DOB, education, socials, a Wikidata/Wikipedia
  link, and a portrait photo where Wikimedia Commons has one. All 222
  Seats are covered, since a missing bio field is just `null`, not an
  integrity problem the way an invented vote would be.

Field-for-field the two do not overlap (checked before writing this): the
merge is a union of two field sets under one key, not a reconciliation of
conflicting facts. Where a Seat is skipped by `mp_profiles.json`,
`mp_profiles` stays absent on the merged record rather than backfilling it
with a guess — the same rule ADR 0009 applies to `mp_profiles.json` itself
applies to this merge.

Run by hand, same cadence as `build_mp_profiles.py` and
`frontend/pipeline/09_politicians.py` — not part of the daily pipeline,
since neither source changes on a daily cadence.

    .venv/bin/python scripts/merge_mp_profiles.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MP_PROFILES_PATH = REPO_ROOT / "data" / "mp_profiles.json"
POLITICIANS_PATH = REPO_ROOT / "frontend" / "public" / "data" / "politicians.json"
OUTPUT_PATH = REPO_ROOT / "frontend" / "public" / "data" / "mp-profiles-merged.json"

# `coalition` on each source answers a different question, not the same one
# checked twice: `mp_profiles.json`'s is the GE15 ballot-line coalition (its
# own `unverified.party` note says so explicitly — see e.g. P.146/Syed
# Saddiq, "MUDA" at the Nov 2022 ballot vs. "PH" today per Wikidata).
# `politicians.json`'s is Wikidata's current-affiliation snapshot. Neither is
# wrong; they're not the same fact, so the merge keeps both under their own
# namespace rather than forcing them to agree.
_COALITION_NOTE_FIELDS = ("coalition",)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge() -> dict[str, Any]:
    mp_profiles = _load(MP_PROFILES_PATH)
    politicians = _load(POLITICIANS_PATH)

    legislative = mp_profiles["profiles"]
    bios = politicians["mps"]

    all_codes = sorted(set(legislative) | set(bios))
    merged: dict[str, Any] = {}
    coalition_differences: list[str] = []

    for code in all_codes:
        legislative_record = legislative.get(code)
        bio_record = bios.get(code)

        record: dict[str, Any] = {"code": code}
        if bio_record:
            record["bio"] = bio_record
        if legislative_record:
            record["legislative"] = legislative_record

        if legislative_record and bio_record:
            for field in _COALITION_NOTE_FIELDS:
                ge15_value = legislative_record.get(field)
                current_value = bio_record.get(field)
                if ge15_value and current_value and ge15_value != current_value:
                    coalition_differences.append(
                        f"{code}: {field}_ge15={ge15_value!r} vs "
                        f"{field}_current={current_value!r}"
                    )

        merged[code] = record

    if coalition_differences:
        print(
            f"note: {len(coalition_differences)} Seat(s) have a different "
            "GE15-ballot coalition than Wikidata's current-affiliation "
            "snapshot (not an error — see the module docstring):"
        )
        for line in coalition_differences:
            print(f"  {line}")

    return {
        "meta": {
            "sources": {
                "legislative": "data/mp_profiles.json (scripts/build_mp_profiles.py, ADR 0009)",
                "bio": "frontend/public/data/politicians.json (frontend/pipeline/09_politicians.py)",
            },
            "seats_with_legislative_profile": len(legislative),
            "seats_with_bio_profile": len(bios),
            "seats_with_both": sum(
                1 for r in merged.values() if "bio" in r and "legislative" in r
            ),
            "total_seats": len(all_codes),
        },
        "mps": merged,
    }


def main() -> None:
    output = merge()
    OUTPUT_PATH.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    meta = output["meta"]
    print(
        f"wrote {OUTPUT_PATH}: {meta['total_seats']} Seats, "
        f"{meta['seats_with_both']} with both bio and legislative data, "
        f"{meta['seats_with_legislative_profile']} with legislative only, "
        f"{meta['seats_with_bio_profile']} with bio only"
    )


if __name__ == "__main__":
    main()
