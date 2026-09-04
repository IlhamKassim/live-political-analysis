"""Copy `public/projection.json` for the frontend's projection view.

Step 4 prerequisite (see `docs/design/mypolitik-new-views-spec.md`'s
Projection view). `public/projection.json` (`src/lpa/public_export.py`) is
the one source of truth for the Projection as JSON — this script copies it
verbatim into `frontend/`, the same way `export_bills_for_frontend.py`
copies `data/bills.json`, rather than reshaping or re-deriving anything.

Run by hand, after `python -m lpa.public_export` (or the daily pipeline) has
refreshed `public/projection.json`:

    .venv/bin/python scripts/export_projection_for_frontend.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "public" / "projection.json"
OUTPUT_PATH = REPO_ROOT / "frontend" / "public" / "data" / "projection.json"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE_PATH, OUTPUT_PATH)
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    print(f"wrote {OUTPUT_PATH}: {len(payload['seats'])} Seat(s)")


if __name__ == "__main__":
    main()
