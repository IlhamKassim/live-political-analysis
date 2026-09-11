"""Only one full-page in-app view may be open at a time.

Each page's opener used to close the others through its own hand-copied list.
Coalitions' list missed GE16 Process, so going Process -> Coalitions drew both
pages on top of each other. Openers now go through one shared list,
`PAGE_CLOSERS` / `closeOtherPages()` in app.js; these tests keep it complete.
"""

import re
from pathlib import Path

APP_JS = (Path(__file__).resolve().parents[1] / "frontend" / "public" / "app.js").read_text()

# opener function -> the PAGE_CLOSERS key it must keep open
OPENERS = {
    "openPoliticians": "politicians",
    "openNewsPage": "news",
    "openDewanPage": "dewan",
    "openBillsPage": "bills",
    "openSentimentPage": "sentiment",
    "openProjectionPage": "projection",
    "openMethodologyPage": "methodology",
    "openGlossaryPage": "glossary",
    "openCoalitionsPage": "coalitions",
    "openProcessPage": "process",
}


def _function_body(name: str) -> str:
    match = re.search(rf"^(?:async )?function {name}\(.*?^\}}", APP_JS, re.DOTALL | re.MULTILINE)
    assert match, f"{name} not found in app.js"
    return match.group(0)


def test_every_page_close_function_is_in_the_shared_list():
    closers = set(re.findall(r"^function (close\w+)\(options = \{\}\)", APP_JS, re.MULTILINE))
    table = re.search(r"const PAGE_CLOSERS = \{(.*?)\};", APP_JS, re.DOTALL)
    assert table, "PAGE_CLOSERS missing from app.js"
    listed = set(re.findall(r"=> (close\w+)\(o\)", table.group(1)))
    page_closers = {c for c in closers if c != "closePrnMode"}
    assert page_closers - listed == set(), "page close function missing from PAGE_CLOSERS"
    keys = set(re.findall(r"^\s+(\w+): \(o\)", table.group(1), re.MULTILINE))
    assert keys == set(OPENERS.values())


def test_every_page_opener_closes_all_other_pages():
    for opener, key in OPENERS.items():
        body = _function_body(opener)
        assert f'closeOtherPages("{key}")' in body, f"{opener} must call closeOtherPages({key!r})"
