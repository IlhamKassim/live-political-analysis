"""Export `data/bills.json` for the frontend's bill tracker view.

Step 4 prerequisite (see `docs/design/mypolitik-new-views-spec.md`'s View 2
— Bill tracker). `frontend/` (mypolitik) has no bill data of its own;
`data/bills.json` (`scripts/build_bill_tracker.py`, ADR 0010) is the only
source and is copied verbatim, not reshaped — the frontend reads the same
`{"bills": {...}}` structure this repo's own pages already read. No field
is renamed, translated, or paraphrased; `stage` stays Parliament's own
literal status label and `summary` stays a verbatim excerpt, per ADR 0010.

Run by hand, same cadence as `scripts/build_bill_tracker.py` (not part of
the daily pipeline on its own, since it's just a copy of that script's
output):

    .venv/bin/python scripts/export_bills_for_frontend.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "data" / "bills.json"
OUTPUT_PATH = REPO_ROOT / "frontend" / "public" / "data" / "bills.json"


def main() -> None:
    shutil.copyfile(SOURCE_PATH, OUTPUT_PATH)
    bills = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))["bills"]
    print(f"wrote {OUTPUT_PATH}: {len(bills)} Bill(s)")


if __name__ == "__main__":
    main()
