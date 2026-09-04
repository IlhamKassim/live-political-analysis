#!/usr/bin/env python3
"""Hansard Dewan Rakyat → per-seat "In Parliament" activity (hansard-dewan.json).

Source: hansard.parlimen.gov.my (official Digital Hansard, Parliament of Malaysia).
No public API — the catalog and every sitting ship complete inside the page's
__NEXT_DATA__ JSON, so this is a polite SSR scrape:

  catalog /katalog/dewan-rakyat      → archive tree → P15 sitting dates
  reader  /hansard/dewan-rakyat/DATE → pageProps.speeches (the whole day,
          ⚠️ DATE without the dr_ prefix — the prefixed form 500s)

Speaker → seat join, two passes over the whole corpus:
  1. authors like "Tuan Khoo Poay Tiong [Kota Melaka]" carry the seat in
     brackets → join to seats-parlimen.json by normalized name; every match
     also teaches us author_id → seat.
  2. ministers speak under portfolio titles ("Menteri Ekonomi [person]") with
     the SAME author_id as their constituency persona → attributed via the
     author_id map learned in pass 1.

Cache: pipeline/raw/hansard/dr_DATE.json — finals are immutable, drafts are
refetched only with --refresh-drafts (Hansard revises drafts until is_final).

Usage:
  python3 pipeline/15_hansard.py                 # incremental (new sittings only)
  python3 pipeline/15_hansard.py --limit 5       # first N missing sittings
  python3 pipeline/15_hansard.py --refresh-drafts
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "pipeline" / "raw" / "hansard"
SEATS = ROOT / "public" / "data" / "seats-parlimen.json"
ALIASES = ROOT / "pipeline" / "hansard_seat_aliases.json"
OUT = ROOT / "public" / "data" / "hansard-dewan.json"

BASE = "https://hansard.parlimen.gov.my"
UA = "MyPolitik-pipeline/1.0 (mypolitik.xyz; data attribution to Hansard Parlimen)"
PARLIAMENT = "15"
THROTTLE_S = 1.2
EXCERPT_MAX = 300
EXCERPT_MIN = 120
EXCERPTS_PER_SEAT = 2

NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
BRACKET_RE = re.compile(r"\[([^\[\]]+)\]\s*$")
# Presiding-officer turns are procedure ("Silakan…"), not debate — counting them
# buries the Deputy Speakers' seats under thousands of chairing interjections
# (P.078/P.211 topped the table 3–4× over before this filter). Their genuine
# floor speeches still count: those carry their own name, not the chair role.
CHAIR_RE = re.compile(
    r"^\s*(?:tuan|puan|timbalan)\s+(?:yang\s+di-?pertua|pengerusi)\b", re.I
)


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 — retry any transport error
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {url}: {last}")


def next_data(html):
    m = NEXT_DATA_RE.search(html)
    if not m:
        raise RuntimeError("no __NEXT_DATA__ in page")
    return json.loads(m.group(1))


def catalog_sittings():
    """All P15 Dewan Rakyat sittings from the catalog archive tree, sorted by date."""
    page = next_data(fetch(f"{BASE}/katalog/dewan-rakyat"))
    archive = page["props"]["pageProps"]["archive"][PARLIAMENT]
    sittings = []
    for term_key, term in archive.items():
        if not isinstance(term, dict):
            continue
        for meet_key, meet in term.items():
            if not isinstance(meet, dict) or "sitting_list" not in meet:
                continue
            for s in meet["sitting_list"]:
                sittings.append(
                    {
                        "date": s["date"],
                        "filename": s["filename"],
                        "is_final": bool(s.get("is_final")),
                        "penggal": term_key,
                        "mesyuarat": meet_key,
                    }
                )
    sittings.sort(key=lambda s: s["date"])
    return sittings


def cached(sit):
    p = RAW / f"{sit['filename']}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — corrupt cache = refetch
        return None


def fetch_sitting(sit):
    page = next_data(fetch(f"{BASE}/hansard/dewan-rakyat/{sit['date']}"))
    props = page["props"]["pageProps"]
    doc = {
        "date": sit["date"],
        "filename": sit["filename"],
        "penggal": sit["penggal"],
        "mesyuarat": sit["mesyuarat"],
        "is_final": bool(props.get("is_final")),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "speeches": props.get("speeches") or [],
    }
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{sit['filename']}.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    return doc


def norm(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'").replace("`", "'").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


def seat_lookup():
    seats = json.loads(SEATS.read_text())
    rows = seats if isinstance(seats, list) else seats.get("seats", [])
    by_name = {norm(r["name"]): r["code"] for r in rows}
    if ALIASES.exists():
        for alias, code in json.loads(ALIASES.read_text()).items():
            by_name[norm(alias)] = code
    return by_name


HONORIFICS = frozenset(
    "yb yab tuan puan dato dato' datuk datin seri sri wira paduka haji hajah hj "
    "dr ir ts prof kapten mejar leftenan jeneral (b) b bin binti a/l a/p al ap".split()
)


def person_tokens(s):
    """Normalized name tokens with honorifics dropped ('@' aliases keep both parts)."""
    return frozenset(t for t in norm(s.replace("@", " ")).split() if t not in HONORIFICS)


def roster_lookup():
    """Current-MP name tokens → seat code (only names unique enough to trust)."""
    pol = json.loads((ROOT / "public" / "data" / "politicians.json").read_text())
    entries = []
    for code, mp in pol.get("mps", {}).items():
        toks = person_tokens(mp.get("name") or "")
        if toks:
            entries.append((toks, code))
    return entries


def match_person(bracket, roster):
    """Unique roster MP whose full name tokens all appear in the bracketed name."""
    btoks = person_tokens(bracket)
    hits = [code for toks, code in roster if toks <= btoks]
    return hits[0] if len(hits) == 1 else None


def flatten(node, section, out):
    """speeches is a mixed list: speech dicts + {section title: [children]} dicts."""
    if isinstance(node, list):
        for x in node:
            flatten(x, section, out)
    elif isinstance(node, dict):
        if "speech" in node:
            out.append((section, node))
        else:
            for title, child in node.items():
                flatten(child, title if section is None else section, out)


def clean_text(s):
    s = re.sub(r"\*+", "", s)  # markdown emphasis markers
    return " ".join(s.split())


def excerpt(s):
    s = clean_text(s)
    if len(s) <= EXCERPT_MAX:
        return s
    cut = s[:EXCERPT_MAX].rsplit(" ", 1)[0]
    return cut + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="fetch at most N missing sittings")
    ap.add_argument("--refresh-drafts", action="store_true", help="refetch cached non-final sittings")
    ap.add_argument("--no-fetch", action="store_true", help="aggregate from cache only")
    args = ap.parse_args()

    sittings = catalog_sittings()
    print(f"catalog: {len(sittings)} P{PARLIAMENT} Dewan Rakyat sittings "
          f"({sittings[0]['date']} → {sittings[-1]['date']})", file=sys.stderr)

    docs, fetched = [], 0
    for sit in sittings:
        doc = cached(sit)
        stale_draft = doc and not doc.get("is_final") and (sit["is_final"] or args.refresh_drafts)
        if (doc is None or stale_draft) and not args.no_fetch:
            if args.limit and fetched >= args.limit:
                if doc is None:
                    continue
            else:
                print(f"  fetch {sit['date']}"
                      f"{' (draft refresh)' if stale_draft else ''}", file=sys.stderr)
                doc = fetch_sitting(sit)
                fetched += 1
                time.sleep(THROTTLE_S)
        if doc:
            docs.append(doc)
    print(f"aggregating {len(docs)} sittings ({fetched} newly fetched)", file=sys.stderr)

    by_name = seat_lookup()
    roster = roster_lookup()

    # pass 1 — flatten everything; learn author_id → seat from bracket sightings
    all_turns = []  # (date, section, author, author_id, speech)
    id_to_seat = {}
    for doc in docs:
        flat = []
        flatten(doc["speeches"], None, flat)
        for section, sp in flat:
            author = sp.get("author")
            if not author or sp.get("is_annotation") or CHAIR_RE.match(author):
                continue
            all_turns.append((doc["date"], section, author, sp.get("author_id"), sp.get("speech") or ""))
            m = BRACKET_RE.search(author)
            if m and sp.get("author_id") is not None:
                code = by_name.get(norm(m.group(1)))
                if code:
                    id_to_seat[sp["author_id"]] = code

    # pass 2 — attribute every turn to a seat
    unmatched = {}
    seats = {}
    for date, section, author, author_id, speech in all_turns:
        code = None
        m = BRACKET_RE.search(author)
        if m:
            code = by_name.get(norm(m.group(1)))
        if code is None and author_id is not None:
            code = id_to_seat.get(author_id)
        if code is None and m:
            # role speeches ("Perdana Menteri [Dato' Seri Anwar bin Ibrahim]") bracket
            # the PERSON — match against the current roster, unique matches only
            code = match_person(m.group(1), roster)
        if code is None:
            if m:  # still unknown — spelling variant worth an alias, or an ex-MP
                unmatched[m.group(1)] = unmatched.get(m.group(1), 0) + 1
            continue
        rec = seats.setdefault(code, {"turns": 0, "qa": 0, "dates": set(), "recent": []})
        rec["turns"] += 1
        sec_u = (section or "").upper()
        if "PERTANYAAN" in sec_u and ("JAWAB LISAN" in sec_u or "JAWAB MULUT" in sec_u):
            rec["qa"] += 1
        rec["dates"].add(date)
        text = clean_text(speech)
        if len(text) >= EXCERPT_MIN:
            rec["recent"].append({"d": date, "sec": (section or "")[:80], "t": excerpt(speech)})

    out_seats = {}
    for code, rec in seats.items():
        recent = sorted(rec["recent"], key=lambda e: e["d"])[-EXCERPTS_PER_SEAT:]
        out_seats[code] = {
            "turns": rec["turns"],
            "qa": rec["qa"],
            "sittings": len(rec["dates"]),
            "last": max(rec["dates"]),
            "excerpts": list(reversed(recent)),  # newest first
        }

    finals = sum(1 for d in docs if d.get("is_final"))
    out = {
        "meta": {
            "source": "Hansard Parlimen (rasmi) · hansard.parlimen.gov.my",
            "house": "dewan-rakyat",
            "parliament": int(PARLIAMENT),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sittings": len(docs),
            "final": finals,
            "draft": len(docs) - finals,
            "from": docs[0]["date"] if docs else None,
            "to": docs[-1]["date"] if docs else None,
            "note": "Turns/Q&A counted from the official transcript; draft sittings may still be revised by Parliament.",
        },
        "seats": dict(sorted(out_seats.items())),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    size = OUT.stat().st_size
    print(f"wrote {OUT.name}: {len(out_seats)} seats, {size/1024:.0f}KB", file=sys.stderr)

    if unmatched:
        top = sorted(unmatched.items(), key=lambda kv: -kv[1])[:15]
        print("unmatched brackets (add real seat variants to pipeline/hansard_seat_aliases.json;"
              " person-name brackets on role speeches are expected and resolved via author_id):",
              file=sys.stderr)
        for name, n in top:
            print(f"  {n:4d}x {name}", file=sys.stderr)


if __name__ == "__main__":
    main()
