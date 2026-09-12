"""The map app's HTML shell, `frontend/public/index.html`.

`daily.yml` copies `frontend/public/` to `public/app/` with a plain `cp -r`,
so whatever is in this file is what the browser gets at `/app/`. That puts it
outside `test_politikku_site_links.py`, which only walks pages a renderer can
build.
"""

from __future__ import annotations

import re
from pathlib import Path

APP_SHELL = Path(__file__).resolve().parents[1] / "frontend/public/index.html"


def test_the_app_shell_markup_has_no_escape_sequences_left_as_text():
    """A sidebar link was once inserted with a `\\n` that stayed two literal
    characters instead of becoming a line break, so the map app's menu showed a
    stray `\\n` row between GE16 and GE16 Process. An escape written as text is
    always a bad edit, never markup, so none belongs outside a script.
    """
    markup = re.sub(
        r"<script\b.*?</script>", "", APP_SHELL.read_text(), flags=re.DOTALL | re.IGNORECASE
    )

    for escape in ("\\n", "\\t", "\\r"):
        assert escape not in markup, f"{escape} appears as text in {APP_SHELL.name}"
