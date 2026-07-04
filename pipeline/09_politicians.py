#!/usr/bin/env python3
"""Bake the politician roster for the 222 federal MPs (15th Parliament).

Source of truth for identity/party/coalition: our own trusted results-ge15.json
(Thevesh, already normalised to our coalition codes + colours). ENRICHMENT
(photo, date of birth, education, socials, Wikipedia bio) comes from Wikidata +
Wikimedia Commons + the Wikipedia REST summary API — the only machine-readable,
licence-clean sources (official Parliament portraits are govt-copyright and off
limits). Every Wikimedia request carries a descriptive User-Agent (403 otherwise).

Provenance doctrine (same as 04/06): we store sourced facts + verbatim Wikipedia
lead paragraphs with attribution and a link back — never paraphrased or invented.
Photos are MIRRORED to public/assets/politicians/ (Wikimedia asks reusers to copy,
not hotlink) with per-image attribution read from Commons extmetadata.

Resumable: SPARQL + each image + each bio are cached under pipeline/raw/politicians/
so an interrupted run resumes and re-runs are cheap.

Output: public/data/politicians.json  (keyed by parliament seat code P.001..P.222)
"""
import hashlib
import io
import json
import os
import re
import time
import urllib.parse
import urllib.request

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEATS = os.path.join(ROOT, "public", "data", "seats-parlimen.json")
RESULTS = os.path.join(ROOT, "public", "data", "results-ge15.json")
OUT = os.path.join(ROOT, "public", "data", "politicians.json")
PHOTO_DIR = os.path.join(ROOT, "public", "assets", "politicians")
CACHE = os.path.join(ROOT, "pipeline", "raw", "politicians")
CROSSWALK = os.path.join(ROOT, "pipeline", "wikidata_seat_map.json")

UA = "MyPolitik/1.0 (https://mypolitik.xyz; danial.alias1@gmail.com) politician-roster"
WDQS = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Tanjong (Wikidata) vs Tanjung (our DOSM name) etc.
NAME_ALIAS = {"tanjongpiai": "tanjungpiai"}

SPARQL = """
SELECT ?person ?personLabel ?district ?districtLabel ?partyLabel ?coalLabel ?image ?dob ?start
       ?eduLabel ?fb ?ig ?tw ?enTitle ?msTitle WHERE {
  ?person p:P39 ?st .
  ?st ps:P39 wd:Q21290861 ; pq:P2937 wd:Q115641712 .
  OPTIONAL { ?st pq:P768 ?district . }
  OPTIONAL { ?st pq:P580 ?start . }
  OPTIONAL { ?st pq:P4100 ?coal . }
  OPTIONAL { ?person wdt:P102 ?party . }
  OPTIONAL { ?person wdt:P18 ?image . }
  OPTIONAL { ?person wdt:P569 ?dob . }
  OPTIONAL { ?person wdt:P69 ?edu . }
  OPTIONAL { ?person wdt:P2013 ?fb . } OPTIONAL { ?person wdt:P2003 ?ig . } OPTIONAL { ?person wdt:P2002 ?tw . }
  OPTIONAL { [] schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?enTitle . }
  OPTIONAL { [] schema:about ?person ; schema:isPartOf <https://ms.wikipedia.org/> ; schema:name ?msTitle . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,ms". }
}
"""


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("utf-8", "replace")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def namekey(s):
    s = (s or "").lower()
    s = re.sub(r"\b(bin|binti|binte|bt|a/l|a/p|al|ap|anak|@|dato|datuk|seri|haji|hj|ir|dr|tan|sri)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def v(row, k):
    return row.get(k, {}).get("value")


def fetch_sparql():
    cache = os.path.join(CACHE, "sparql.json")
    if os.path.exists(cache):
        return json.load(open(cache))
    url = WDQS + "?" + urllib.parse.urlencode({"format": "json", "query": SPARQL})
    rows = json.loads(get(url))["results"]["bindings"]
    json.dump(rows, open(cache, "w"))
    return rows


def merge_people(rows):
    """One record per person, then keep the latest-starting holder per district."""
    people = {}
    for r in rows:
        p = v(r, "person")
        e = people.setdefault(p, {
            "qid": p.rsplit("/", 1)[-1], "name": v(r, "personLabel"),
            "district": v(r, "districtLabel"), "image": None, "dob": v(r, "dob"),
            "edu": set(), "starts": set(),
            "fb": v(r, "fb"), "ig": v(r, "ig"), "tw": v(r, "tw"),
            "en": v(r, "enTitle"), "ms": v(r, "msTitle"),
        })
        if v(r, "image"):
            e["image"] = v(r, "image")
        if v(r, "start"):
            e["starts"].add(v(r, "start"))
        if v(r, "eduLabel") and not re.match(r"^Q\d+$", v(r, "eduLabel") or ""):
            e["edu"].add(v(r, "eduLabel"))
    bydist = {}
    for e in people.values():
        d = e["district"]
        if not d:
            continue
        latest = max(e["starts"]) if e["starts"] else ""
        if d not in bydist or latest > bydist[d][1]:
            bydist[d] = (e, latest)
    return {d: e for d, (e, _) in bydist.items()}


def crosswalk(mps, seats):
    by_seatname = {}
    for s in seats:
        by_seatname.setdefault(norm(s["name"]), s["code"])
    xwalk, out = {}, {}
    for dist, e in mps.items():
        key = NAME_ALIAS.get(norm(dist), norm(dist))
        code = by_seatname.get(key)
        if not code:
            print(f"  ! unmatched district: {dist} ({e['name']})")
            continue
        out[code] = e
        xwalk[e["qid"]] = code
    json.dump(xwalk, open(CROSSWALK, "w"), indent=1)
    return out


def commons_filename_from_url(image_url):
    # P18 value is a Special:FilePath URL; the filename is the last path segment
    return urllib.parse.unquote(image_url.rsplit("/", 1)[-1])


def fetch_photo(code, image_url):
    """Download a 320px Commons thumbnail, convert to webp, return attribution."""
    meta_cache = os.path.join(CACHE, f"{code}.imginfo.json")
    webp = os.path.join(PHOTO_DIR, f"{code}.webp")
    fname = commons_filename_from_url(image_url)
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
            "license_url": em.get("LicenseUrl", {}).get("value") or "",
            "file": fname,
        }
        json.dump(info, open(meta_cache, "w"))
        time.sleep(0.2)
    if not info.get("thumb"):
        return None
    if not os.path.exists(webp):
        try:
            raw = get(info["thumb"], binary=True)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((320, 320))
            im.save(webp, "WEBP", quality=82, method=6)
            time.sleep(0.15)
        except Exception as ex:
            print(f"  ! photo {code} ({fname}): {ex}")
            return None
    credit = info["artist"] or "Wikimedia Commons"
    if info["license"]:
        credit += f" · {info['license']}"
    return {"path": f"assets/politicians/{code}.webp", "credit": credit,
            "file": info["file"], "license_url": info["license_url"]}


def fetch_bio(lang, title):
    if not title:
        return None
    cache = os.path.join(CACHE, f"bio.{lang}.{hashlib.md5(title.encode()).hexdigest()[:12]}.json")
    if os.path.exists(cache):
        d = json.load(open(cache))
    else:
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title, safe="")
        try:
            d = json.loads(get(url))
        except Exception:
            d = {}
        json.dump(d, open(cache, "w"))
        time.sleep(0.2)
    extract = (d.get("extract") or "").strip()
    if not extract or d.get("type") == "disambiguation":
        return None
    page = (d.get("content_urls", {}).get("desktop", {}) or {}).get("page")
    return {"extract": extract[:600], "url": page or f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"}


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    seats = json.load(open(SEATS))["seats"]
    results = json.load(open(RESULTS))

    rows = fetch_sparql()
    mps = merge_people(rows)
    print(f"SPARQL: {len(mps)} current MPs")
    matched = crosswalk(mps, seats)
    assert len(matched) == 222, f"expected 222 seats mapped, got {len(matched)}"

    out = {}
    photos = bios = 0
    for i, (code, e) in enumerate(sorted(matched.items()), 1):
        res = results.get(code, {})
        ballot = res.get("name") or ""
        # Wikidata common name preferred (recognisable); fall back to ballot when it
        # failed to resolve to a real label (came back as a bare QID).
        wd_name = e["name"] if e["name"] and not re.match(r"^Q\d+$", e["name"]) else ""
        name = wd_name or ballot
        rec = {
            "name": name,
            "party": res.get("party") or None,
            "coalition": res.get("coalition") or None,
            "dob": e["dob"][:10] if e["dob"] else None,
            "education": sorted(e["edu"])[0] if e["edu"] else None,
            "socials": {k: e[k] for k in ("fb", "ig", "tw") if e.get(k)} or None,
            "wikidata": f"https://www.wikidata.org/wiki/{e['qid']}",
            "photo": None, "photo_credit": None, "wikipedia": None,
        }
        if wd_name and namekey(ballot) != namekey(wd_name):
            rec["ballot_name"] = ballot
        if e["image"]:
            ph = fetch_photo(code, e["image"])
            if ph:
                rec["photo"] = ph["path"]
                rec["photo_credit"] = ph["credit"]
                rec["photo_license_url"] = ph["license_url"]
                photos += 1
        wiki = {}
        for lang, title in (("en", e["en"]), ("ms", e["ms"])):
            b = fetch_bio(lang, title)
            if b:
                wiki[lang] = b
        if wiki:
            rec["wikipedia"] = wiki
            bios += 1
        out[code] = rec
        if i % 40 == 0:
            print(f"  {i}/222  (photos {photos}, bios {bios})")

    payload = {
        "meta": {
            "roster": "Federal MPs, 15th Parliament (222 seats)",
            "identity": "results-ge15.json (Thevesh / SPR / DOSM)",
            "enrichment": "Wikidata · Wikimedia Commons · Wikipedia (CC BY-SA / see per-photo credit)",
        },
        "mps": out,
    }
    json.dump(payload, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    print(f"politicians: 222 MPs, {photos} photos, {bios} bios -> {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
