#!/usr/bin/env python3
"""Bake linked news headlines for PRN16 Johor candidates.

Default source path: publisher RSS feeds listed in pipeline/news_sources.json.
Optional fallback: GDELT 2.0 DOC API via --gdelt.

The output intentionally stores TITLE + LINK + SOURCE + DATE ONLY. MyPolitik
links out to publishers and never republishes article bodies. Matching is
conservative: candidate headlines require a multi-token candidate alias and
Johor/election context; general Johor election headlines are stored separately
under _general.

Output:
  public/data/candidate-news-johor.json

Shape:
  {
    "1_N.01": {
      "Datuk Zahari Sarip": [{"t": title, "u": url, "s": domain, "d": "YYYY-MM-DD"}]
    },
    "_general": {
      "Johor election": [{"t": title, "u": url, "s": domain, "d": "YYYY-MM-DD"}]
    }
  }

Run:
  python3 pipeline/06_candidate_news.py
  python3 pipeline/06_candidate_news.py --gdelt
"""
import argparse
import email.utils
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRN16 = os.path.join(ROOT, "public", "data", "prn16-johor.json")
OUT = os.path.join(ROOT, "public", "data", "candidate-news-johor.json")
POLITICAL_OUT = os.path.join(ROOT, "public", "data", "political-news.json")
SOURCES = os.path.join(ROOT, "pipeline", "news_sources.json")

API = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMESPAN = "6weeks"
MAX_PER_CANDIDATE = 3
MAX_GENERAL = 16
THROTTLE = 3.0
CAMPAIGN_START = "2026-06-01"

HONORIFICS = {
    "yb", "datuk", "dato", "dato'", "datukseri", "datoseri", "seri", "dr",
    "haji", "hj", "ir", "ts", "kapt", "kapten", "ustaz", "cikgu", "puan",
    "tuan", "sr",
}

ELECTION_TERMS = [
    "johor", "prn", "poll", "polls", "election", "state election",
    "by-election", "candidate", "candidates", "nomination", "campaign",
    "manifesto", "seat", "seats", "voter", "voters", "ballot",
    "pilihan raya", "pilihanraya", "calon", "kempen", "manifesto",
    "kerusi", "undi", "pengundi", "dun", "spr",
]

POLITICAL_TERMS = [
    "umno", "mca", "mic", "dap", "pkr", "amanah", "pas", "bersatu", "muda",
    "psm", "bn", "ph", "pn", "barisan", "pakatan", "perikatan", "bersama",
]

NATIONAL_POLITICS_TERMS = ELECTION_TERMS + POLITICAL_TERMS + [
    "anwar", "muhyiddin", "zahid", "guan eng", "rafizi", "gobind",
    "parliament", "parlimen", "dewan rakyat", "dewan negara", "cabinet",
    "minister", "ministry", "menteri", "kerajaan", "opposition",
    "pembangkang", "mp", "adun", "assemblyman", "assemblywoman",
    "chief minister", "menteri besar", "prime minister", "perdana menteri",
]


def folded(s):
    s = html.unescape(str(s or ""))
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s.lower()


def words(s):
    return re.findall(r"[a-z0-9]+", folded(s))


def clean_name(s):
    toks = [t for t in words(s) if t not in HONORIFICS and len(t) > 1]
    return toks


def strip_tags(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", str(s or ""))
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def canonical_url(u):
    if not u:
        return ""
    p = urllib.parse.urlparse(u.strip())
    return urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", "", ""))


def domain_of(u, fallback=""):
    try:
        host = urllib.parse.urlparse(u).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return fallback


def parse_date(s):
    s = str(s or "").strip()
    if not s:
        return None
    try:
        return email.utils.parsedate_to_datetime(s).date().isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        return None


def date_ok(d):
    return not d or d >= CAMPAIGN_START


def fetch_text(url, timeout=18):
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikNews/1.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def item_text(item):
    return " ".join([item.get("title", ""), item.get("summary", ""), item.get("source", "")])


def term_present(folded_text, term):
    ft = folded(term)
    if not ft:
        return False
    if " " in ft or len(ft) > 3:
        return ft in folded_text
    return re.search(rf"\b{re.escape(ft)}\b", folded_text) is not None


def political_context(text, seat_name=""):
    f = folded(text)
    if seat_name and folded(seat_name) in f:
        return True
    return any(term_present(f, term) for term in ELECTION_TERMS + POLITICAL_TERMS)


def general_johor_election_item(item):
    f = folded(item.get("title", ""))
    return term_present(f, "johor") and any(
        term_present(f, term) for term in ELECTION_TERMS if term != "johor"
    )


def national_political_item(item):
    f = folded(item_text(item))
    return any(term_present(f, term) for term in NATIONAL_POLITICS_TERMS)


def seat_context_item(item, seat_name):
    toks = clean_name(seat_name)
    if not toks:
        return False
    text_words = set(words(item_text(item)))
    if not all(t in text_words for t in toks):
        return False
    f = folded(item_text(item))
    return term_present(f, "johor") or any(term_present(f, term) for term in ELECTION_TERMS)


def aliases_for(candidate):
    aliases = []
    for val in (candidate.get("name"), candidate.get("ballot_name")):
        toks = clean_name(val)
        if len(toks) >= 2:
            aliases.append(toks)
        if len(toks) >= 3:
            aliases.append([toks[0], toks[-1]])
    out, seen = [], set()
    for toks in aliases:
        key = tuple(toks)
        if key not in seen:
            seen.add(key)
            out.append(toks)
    return out


def candidate_matches(item, candidate, seat_name):
    text_words = set(words(item_text(item)))
    if not political_context(item_text(item), seat_name):
        return False
    for toks in aliases_for(candidate):
        if all(t in text_words for t in toks):
            return True
    return False


def rss_find_text(node, names):
    for name in names:
        found = node.find(name)
        if found is not None and found.text:
            return found.text
    for child in list(node):
        tag = child.tag.split("}", 1)[-1].lower()
        if tag in names and child.text:
            return child.text
    return ""


def parse_feed(xml_text, source):
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    nodes = root.findall(".//item")
    if not nodes:
        nodes = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out = []
    for node in nodes:
        title = re.sub(r"\s+", " ", rss_find_text(node, ["title"]).strip())
        link = rss_find_text(node, ["link"]).strip()
        if not link:
            for child in list(node):
                if child.tag.endswith("link") and child.attrib.get("href"):
                    link = child.attrib["href"]
                    break
        date = parse_date(rss_find_text(node, ["pubDate", "published", "updated", "date"]))
        summary = strip_tags(rss_find_text(node, ["description", "summary", "encoded"]))
        if not title or not link or not date_ok(date):
            continue
        out.append({
            "title": title[:180],
            "url": link,
            "source": domain_of(link, source.get("name", "")),
            "source_id": source.get("id"),
            "source_name": source.get("name"),
            "lang": source.get("lang"),
            "date": date,
            "summary": summary,
        })
    return out


def fetch_feed_items(sources):
    all_items = []
    for source in sources:
        if source.get("kind") != "rss":
            continue
        try:
            xml_text = fetch_text(source["url"])
            items = parse_feed(xml_text, source)
            print(f"  feed {source['id']}: {len(items)} usable items")
            all_items.extend(items)
        except Exception as e:
            print(f"  ! feed {source.get('id', source.get('url'))}: {e}", file=sys.stderr)
    return dedupe_items(all_items)


def to_public_item(item):
    return {
        "t": item["title"][:160],
        "u": item["url"],
        "s": item.get("source") or domain_of(item.get("url")),
        "d": item.get("date"),
    }


def to_political_item(item, **extra):
    out = to_public_item(item)
    if item.get("source_id"):
        out["source_id"] = item["source_id"]
    if item.get("source_name"):
        out["source_name"] = item["source_name"]
    if item.get("lang"):
        out["lang"] = item["lang"]
    for k, v in extra.items():
        if v:
            out[k] = v
    return out


def dedupe_items(items):
    out, seen = [], set()
    for item in items:
        key = canonical_url(item.get("url")) or folded(item.get("title"))[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def merge_items(existing, incoming, limit):
    merged, seen = [], set()
    for item in list(existing or []) + list(incoming or []):
        if not item or not item.get("u") or not item.get("t"):
            continue
        key = canonical_url(item["u"]) or folded(item["t"])[:80]
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=lambda x: str(x.get("d") or ""), reverse=True)
    return merged[:limit]


def sort_items(items, limit):
    out = merge_items([], items, limit)
    return out


def apply_feed_matches(news, prn, feed_items):
    matched_candidates = 0
    general = []
    for item in feed_items:
        if general_johor_election_item(item):
            general.append(to_public_item(item))
    if general:
        news.setdefault("_general", {})
        news["_general"]["Johor election"] = merge_items([], general, MAX_GENERAL)

    for code, seat in sorted(prn["seats"].items()):
        for cand in seat.get("candidates", []):
            found = []
            for item in feed_items:
                if candidate_matches(item, cand, seat.get("name", "")):
                    found.append(to_public_item(item))
            if found:
                name = cand["name"]
                news.setdefault(code, {})
                before = len(news[code].get(name, []))
                news[code][name] = merge_items(news[code].get(name, []), found, MAX_PER_CANDIDATE)
                if len(news[code][name]) > before:
                    matched_candidates += 1
    return matched_candidates, len(general)


def build_political_payload(prn, sources, feed_items, compat_news):
    national = [
        to_political_item(item, scope="national")
        for item in feed_items
        if national_political_item(item)
    ]
    johor_election = [
        to_political_item(item, scope="johor", topic="Johor election")
        for item in feed_items
        if general_johor_election_item(item)
    ]

    by_seat = {}
    for code, seat in sorted(prn["seats"].items()):
        found = [
            to_political_item(item, scope="johor", seat=code, seat_name=seat.get("name", ""))
            for item in feed_items
            if seat_context_item(item, seat.get("name", ""))
        ]
        if found:
            by_seat[code] = sort_items(found, 5)

    by_candidate = {}
    for code, by_name in compat_news.items():
        if code.startswith("_") or not isinstance(by_name, dict):
            continue
        rows = {
            name: items for name, items in by_name.items()
            if isinstance(items, list) and items
        }
        if rows:
            by_candidate[code] = rows

    return {
        "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "window_start": CAMPAIGN_START,
        "sources": [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "url": s.get("url"),
                "lang": s.get("lang"),
                "kind": s.get("kind"),
            }
            for s in sources
        ],
        "national": sort_items(national, 80),
        "johor": {
            "election": sort_items(johor_election, 40),
            "by_seat": by_seat,
            "by_candidate": by_candidate,
        },
    }


def fetch_gdelt_news(name):
    q = f'"{name}" johor'
    url = API + "?" + urllib.parse.urlencode({
        "query": q, "mode": "artlist", "format": "json",
        "maxrecords": 6, "timespan": TIMESPAN, "sort": "datedesc",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikNews/1.1"})
    body = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                if attempt == 0:
                    time.sleep(3)
                    continue
                return None
            raise
        except Exception:
            return None
    if body is None:
        return None
    if not body.strip().startswith("{"):
        return []
    arts = json.loads(body).get("articles", [])
    seen, out = set(), []
    for a in arts:
        title = re.sub(r"\s+", " ", a.get("title") or "").strip()
        url_ = a.get("url") or ""
        if not title or not url_:
            continue
        key = title.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        d = a.get("seendate") or ""
        date = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) >= 8 else None
        out.append({"t": title[:160], "u": url_, "s": a.get("domain") or "", "d": date})
        if len(out) >= MAX_PER_CANDIDATE:
            break
    return out


def apply_gdelt_matches(news, prn, limit_candidates=None):
    fetched = set()
    if isinstance(news.get("_done"), list):
        fetched = set(tuple(x.split("|", 1)) for x in news.get("_done", []) if "|" in x)
    for code, by_name in news.items():
        if code.startswith("_") or not isinstance(by_name, dict):
            continue
        for nm in by_name:
            fetched.add((code, nm))

    done = hits = 0
    all_candidates = [(code, c) for code, s in sorted(prn["seats"].items()) for c in s["candidates"]]
    for code, c in all_candidates:
        done += 1
        if limit_candidates and done > limit_candidates:
            break
        if (code, c["name"]) in fetched:
            hits += 1
            continue
        try:
            items = fetch_gdelt_news(c["name"])
        except Exception as e:
            print(f"  ! {c['name']}: {e}", file=sys.stderr)
            items = None
        if items is None:
            time.sleep(1.5)
            continue
        if items:
            news.setdefault(code, {})
            news[code][c["name"]] = merge_items(news[code].get(c["name"], []), items, MAX_PER_CANDIDATE)
            hits += 1
        fetched.add((code, c["name"]))
        if len(fetched) % 10 == 0:
            print(f"  gdelt processed {len(fetched)} ok, {hits} with news")
            news["_done"] = sorted("|".join(x) for x in fetched)
            write_news(news)
        time.sleep(THROTTLE)
    news["_done"] = sorted("|".join(x) for x in fetched)
    return hits


def write_news(news):
    with open(OUT, "w") as f:
        json.dump(news, f, ensure_ascii=False, separators=(",", ":"))


def write_political(payload):
    with open(POLITICAL_OUT, "w") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))


def count_candidate_hits(news):
    return sum(
        1 for code, by_name in news.items()
        if not code.startswith("_") and isinstance(by_name, dict)
        for arr in by_name.values() if isinstance(arr, list) and arr
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gdelt", action="store_true", help="also query GDELT per candidate")
    ap.add_argument("--limit-candidates", type=int, help="cap GDELT candidates for smoke tests")
    ap.add_argument("--no-feeds", action="store_true", help="skip publisher feeds")
    args = ap.parse_args()

    with open(PRN16) as f:
        prn = json.load(f)
    with open(SOURCES) as f:
        sources = json.load(f)

    news = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            news = json.load(f)

    feed_items = []
    if not args.no_feeds:
        feed_items = fetch_feed_items(sources)
        candidate_added, general_seen = apply_feed_matches(news, prn, feed_items)
        print(f"  feeds scanned {len(feed_items)} unique items; candidates +{candidate_added}; general {general_seen}")

    if args.gdelt:
        print("  gdelt enabled")
        apply_gdelt_matches(news, prn, args.limit_candidates)

    write_news(news)
    payload = build_political_payload(prn, sources, feed_items, news)
    write_political(payload)
    kb = os.path.getsize(OUT) // 1024
    political_kb = os.path.getsize(POLITICAL_OUT) // 1024
    total_c = sum(len(s["candidates"]) for s in prn["seats"].values())
    general_n = len(news.get("_general", {}).get("Johor election", []))
    print(
        f"candidate news: {count_candidate_hits(news)}/{total_c} candidate buckets, "
        f"{general_n} general headlines -> {os.path.relpath(OUT, ROOT)} ({kb} KB)"
    )
    print(
        f"political news: {len(payload['national'])} national, "
        f"{len(payload['johor']['election'])} johor election, "
        f"{len(payload['johor']['by_seat'])} seat buckets -> "
        f"{os.path.relpath(POLITICAL_OUT, ROOT)} ({political_kb} KB)"
    )


if __name__ == "__main__":
    main()
