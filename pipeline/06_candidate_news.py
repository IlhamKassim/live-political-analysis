#!/usr/bin/env python3
"""Bake linked news headlines for PRN16 Johor candidates.

Source: GDELT 2.0 DOC API (open license, unlike news-portal RSS). For each
SPR-confirmed candidate we query `"<name>" johor` over the campaign window and
keep up to 3 recent articles — TITLE + LINK + SOURCE + DATE ONLY. We never
paraphrase, summarize, or editorialize; the app shows them as outbound links
with an explicit auto-matched disclaimer (namesakes possible).

Output: public/data/candidate-news-johor.json
  { "1_N.01": { "Zahari Sarip": [ {"t": title, "u": url, "s": domain, "d": "YYYY-MM-DD"} ] } }

Run: python3 pipeline/06_candidate_news.py       (~4 min, throttled)
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRN16 = os.path.join(ROOT, "public", "data", "prn16-johor.json")
OUT = os.path.join(ROOT, "public", "data", "candidate-news-johor.json")

API = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMESPAN = "6weeks"   # campaign window (dissolution was 1 June)
MAX_PER_CANDIDATE = 3
THROTTLE = 5.5   # GDELT free tier rate-limits hard (~1 req/5s); 429s otherwise


def fetch_news(name):
    q = f'"{name}" johor'
    url = API + "?" + urllib.parse.urlencode({
        "query": q, "mode": "artlist", "format": "json",
        "maxrecords": 6, "timespan": TIMESPAN, "sort": "datedesc",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "MyPolitikNews/1.0"})
    body = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(25 * (attempt + 1))   # back off and retry
                continue
            raise
    if body is None:
        return []
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


def main():
    with open(PRN16) as f:
        prn = json.load(f)
    news = {}
    total_c = sum(len(s["candidates"]) for s in prn["seats"].values())
    done = hits = 0
    for code, s in sorted(prn["seats"].items()):
        for c in s["candidates"]:
            done += 1
            try:
                items = fetch_news(c["name"])
            except Exception as e:
                print(f"  ! {c['name']}: {e}", file=sys.stderr)
                items = []
            if items:
                news.setdefault(code, {})[c["name"]] = items
                hits += 1
            if done % 20 == 0:
                print(f"  {done}/{total_c} candidates, {hits} with news")
            time.sleep(THROTTLE)
    with open(OUT, "w") as f:
        json.dump(news, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(OUT) // 1024
    print(f"candidate news: {hits}/{total_c} candidates matched, {len(news)} seats -> {os.path.relpath(OUT, ROOT)} ({kb} KB)")


if __name__ == "__main__":
    main()
