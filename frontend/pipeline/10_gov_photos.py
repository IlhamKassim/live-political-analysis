#!/usr/bin/env python3
"""Bake portraits for the 13 heads of state government (MB/KM/Premier).

Most MBs/KMs are assemblymen, not MPs, so they're absent from politicians.json —
but all have Wikidata items with license-clean Wikimedia Commons portraits (P18),
the same source the MP roster uses. Resolution is name-search + validation
(human, has P18, description mentions Malaysia/the state/the office) and the run
prints a review table — eyeball it before shipping; adjust QID_OVERRIDES on a bad
match. Photos are mirrored (never hotlinked) with per-image attribution.

Output:
  public/assets/politicians/gov-<slug>.webp   (320px, ~13 files)
  public/data/gov-photos.json                 { "<State>": {photo, credit, qid, file} }

Run: python3 pipeline/10_gov_photos.py   (needs Pillow; UA header mandatory)
"""
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CTX = os.path.join(ROOT, "public", "data", "state-context.json")
OUT = os.path.join(ROOT, "public", "data", "gov-photos.json")
PHOTO_DIR = os.path.join(ROOT, "public", "assets", "politicians")
CACHE = os.path.join(ROOT, "pipeline", "raw", "govphotos")
UA = "MyPolitikBot/1.0 (https://mypolitik.xyz; data pipeline; contact via site)"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# hand overrides if the search picks a namesake (state -> QID); none needed so far
QID_OVERRIDES = {}


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("utf-8", "replace")


def wd(params):
    return json.loads(get(WD_API + "?" + urllib.parse.urlencode({**params, "format": "json"})))


def find_person(name, state):
    """Search Wikidata for the person; validate candidates and return (qid, desc, image_file)."""
    cache = os.path.join(CACHE, re.sub(r"[^a-z0-9]+", "-", name.lower()) + ".json")
    if os.path.exists(cache):
        c = json.load(open(cache))
        return c["qid"], c["desc"], c["image"]
    hits = wd({"action": "wbsearchentities", "search": name, "language": "en",
               "uselang": "en", "type": "item", "limit": "8"}).get("search", [])
    state_l = state.lower()
    office_words = ("menteri besar", "chief minister", "premier", "politician")
    best = None
    for h in hits:
        qid = h["id"]
        ent = wd({"action": "wbgetentities", "ids": qid, "props": "claims"})
        claims = (ent.get("entities", {}).get(qid, {}) or {}).get("claims", {})
        human = any((c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id") == "Q5"
                    for c in claims.get("P31", []))
        img = None
        for c in claims.get("P18", []):
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if v:
                img = v
                break
        desc = (h.get("description") or "").lower()
        if not human:
            continue
        score = 0
        if img: score += 2
        if state_l in desc: score += 3
        if any(w in desc for w in office_words): score += 2
        if "malaysia" in desc: score += 1
        if best is None or score > best[0]:
            best = (score, qid, h.get("description") or "", img)
        time.sleep(0.15)
    if not best or best[0] < 2:   # must at least be a photographed human or well-described
        return None, None, None
    _, qid, desc, img = best
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"qid": qid, "desc": desc, "image": img}, open(cache, "w"))
    return qid, desc, img


def fetch_photo(slug, fname):
    """320px Commons thumb -> webp + attribution (same approach as 09_politicians)."""
    meta_cache = os.path.join(CACHE, f"{slug}.imginfo.json")
    webp = os.path.join(PHOTO_DIR, f"gov-{slug}.webp")
    if os.path.exists(meta_cache):
        info = json.load(open(meta_cache))
    else:
        api = COMMONS_API + "?" + urllib.parse.urlencode({
            "action": "query", "titles": "File:" + fname, "prop": "imageinfo",
            "iiprop": "url|extmetadata", "iiurlwidth": "320", "format": "json",
        })
        pages = json.loads(get(api))["query"]["pages"]
        page = next(iter(pages.values()))
        ii = (page.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata", {})
        info = {
            "thumb": ii.get("thumburl") or ii.get("url"),
            "artist": re.sub(r"<[^>]+>", "", (em.get("Artist", {}).get("value") or "")).strip()[:120],
            "license": em.get("LicenseShortName", {}).get("value") or "",
            "file": fname,
        }
        json.dump(info, open(meta_cache, "w"))
        time.sleep(0.2)
    if not info.get("thumb"):
        return None
    if not os.path.exists(webp):
        raw = get(info["thumb"], binary=True)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((320, 320))
        im.save(webp, "WEBP", quality=82, method=6)
        time.sleep(0.15)
    credit = info["artist"] or "Wikimedia Commons"
    if info["license"]:
        credit += f" · {info['license']}"
    return {"photo": f"assets/politicians/gov-{slug}.webp", "credit": credit, "file": info["file"]}


def main():
    os.makedirs(CACHE, exist_ok=True)
    ctx = json.load(open(CTX))
    out = {}
    print(f"{'state':<18} {'name':<26} {'QID':<12} description")
    print("-" * 96)
    for st, entry in ctx["states"].items():
        g = entry.get("gov")
        if not g:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", st.lower()).strip("-")
        qid = QID_OVERRIDES.get(st)
        if qid:
            claims = wd({"action": "wbgetclaims", "entity": qid, "property": "P18"}).get("claims", {})
            img = next((c["mainsnak"]["datavalue"]["value"] for c in claims.get("P18", [])
                        if c.get("mainsnak", {}).get("datavalue")), None)
            desc = "(override)"
        else:
            qid, desc, img = find_person(g["name"], st)
        if not qid:
            print(f"{st:<18} {g['name']:<26} {'—':<12} NOT FOUND")
            continue
        print(f"{st:<18} {g['name']:<26} {qid:<12} {desc}")
        if not img:
            print(f"{'':<18} {'':<26} {'':<12} (no P18 photo)")
            continue
        p = fetch_photo(slug, img)
        if p:
            out[st] = {**p, "qid": qid}
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\ngov photos: {len(out)} portraits -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
