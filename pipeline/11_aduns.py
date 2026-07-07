#!/usr/bin/env python3
"""Bake portraits for current state assemblymen (ADUNs) — all 600 DUN seats.

Per-term ADUN membership is too patchily modelled on Wikidata for a roster query
(most items don't even carry the assembly seat), so this resolves each seat's
CURRENT holder — the winner in results-dun.json, or Johor's 2022 incumbent in
prn16-johor.json — by NAME, with strict validation before accepting:

  required: human (P31=Q5) · has a Commons portrait (P18) · name-key match
            between the official name and the entity label/alias
  score:    "politician" in description +2 · malaysia(n) +2 · the state +2 ·
            assembly/ADUN/exco/MLA/menteri/speaker words +1  → accept at ≥4

Only confident PHOTO matches ship (a wrong-person photo is worse than a
monogram); everything else falls back to the app's initials monogram.
pipeline/adun_photo_overrides.json pins or blocks a seat: {"<code>": "Q..."}
forces an entity, {"<code>": null} blocks the seat entirely.

Output:
  public/assets/politicians/dun/<code>.webp
  public/data/aduns.json  { "<code>": {name, ballot_name, photo, photo_credit, wikidata} }

Run: python3 pipeline/11_aduns.py    (~10 min first run; per-name cache under
pipeline/raw/aduns/. UA header mandatory on every Wikimedia call.)
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
RESULTS = os.path.join(ROOT, "public", "data", "results-dun.json")
PRN16 = os.path.join(ROOT, "public", "data", "prn16-johor.json")
SEATS = os.path.join(ROOT, "public", "data", "seats-dun.json")
OVERRIDES = os.path.join(ROOT, "pipeline", "adun_photo_overrides.json")
OUT = os.path.join(ROOT, "public", "data", "aduns.json")
PHOTO_DIR = os.path.join(ROOT, "public", "assets", "politicians", "dun")
CACHE = os.path.join(ROOT, "pipeline", "raw", "aduns")
UA = "MyPolitikBot/1.0 (https://mypolitik.xyz; data pipeline; contact via site)"
WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

HONORIFICS = r"\b(datuk|dato'?|datin|dr|haji|hajjah|hajah|hj|tuan|puan|ir|ts|tan|sri|seri|yb|prof|ustaz|ustazah|pehin|panglima|wira|paduka|amar|abang)\b"
OFFICE_WORDS = ("assembly", "adun", "mla", "exco", "menteri", "speaker", "legislative")


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read() if binary else r.read().decode("utf-8", "replace")


def wd(params):
    return json.loads(get(WD_API + "?" + urllib.parse.urlencode({**params, "format": "json"})))


def clean_name(s):
    s = re.sub(HONORIFICS, " ", (s or "").lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s.title()


def namekey(s):
    s = re.sub(HONORIFICS, " ", (s or "").lower())
    s = re.sub(r"\b(bin|binti|binte|bt|a/l|a/p|al|ap|anak|@)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def entity_batch(qids):
    """claims (P31/P18) + aliases for up to 50 entities in one call."""
    out = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        ents = wd({"action": "wbgetentities", "ids": "|".join(chunk),
                   "props": "claims|aliases|labels"}).get("entities", {})
        out.update(ents)
        time.sleep(0.12)
    return out


def resolve(name, state_name):
    """Find the ADUN's Wikidata entity; None unless a confident photo match."""
    ck = os.path.join(CACHE, re.sub(r"[^a-z0-9]+", "-", (state_name + "-" + name).lower())[:120] + ".json")
    if os.path.exists(ck):
        c = json.load(open(ck))
        return c.get("qid"), c.get("label"), c.get("image")
    search = clean_name(name)
    hits = wd({"action": "wbsearchentities", "search": search, "language": "en",
               "uselang": "en", "type": "item", "limit": "6"}).get("search", [])
    time.sleep(0.1)
    result = (None, None, None)
    if hits:
        ents = entity_batch([h["id"] for h in hits])
        nk = namekey(name)
        state_l = state_name.lower()
        best = None
        for h in hits:
            ent = ents.get(h["id"]) or {}
            claims = ent.get("claims", {})
            human = any((c.get("mainsnak", {}).get("datavalue", {}).get("value") or {}).get("id") == "Q5"
                        for c in claims.get("P31", []))
            img = next((c["mainsnak"]["datavalue"]["value"] for c in claims.get("P18", [])
                        if c.get("mainsnak", {}).get("datavalue")), None)
            if not human or not img:
                continue
            label = h.get("label") or ""
            aliases = [a.get("value", "") for a in (ent.get("aliases", {}) or {}).get("en", [])]
            lk_ok = any(namekey(x) and (namekey(x) in nk or nk in namekey(x)) for x in [label] + aliases)
            if not lk_ok:
                continue
            desc = (h.get("description") or "").lower()
            score = 0
            if "politician" in desc: score += 2
            if "malaysia" in desc: score += 2
            if state_l in desc: score += 2
            if any(w in desc for w in OFFICE_WORDS): score += 1
            if best is None or score > best[0]:
                best = (score, h["id"], label, img)
        if best and best[0] >= 4:
            result = (best[1], best[2], best[3])
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"qid": result[0], "label": result[1], "image": result[2]}, open(ck, "w"))
    return result


def entity_photo(qid):
    ents = wd({"action": "wbgetentities", "ids": qid, "props": "claims|labels"}).get("entities", {})
    ent = ents.get(qid) or {}
    claims = ent.get("claims", {})
    img = next((c["mainsnak"]["datavalue"]["value"] for c in claims.get("P18", [])
                if c.get("mainsnak", {}).get("datavalue")), None)
    label = ((ent.get("labels", {}) or {}).get("en", {}) or {}).get("value")
    return label, img


def fetch_photo(code, fname):
    slug = code.replace(".", "-")
    meta_cache = os.path.join(CACHE, f"{slug}.imginfo.json")
    webp = os.path.join(PHOTO_DIR, f"{slug}.webp")
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
        }
        json.dump(info, open(meta_cache, "w"))
        time.sleep(0.15)
    if not info.get("thumb"):
        return None
    if not os.path.exists(webp):
        try:
            raw = get(info["thumb"], binary=True)
            im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((320, 320))
            os.makedirs(PHOTO_DIR, exist_ok=True)
            im.save(webp, "WEBP", quality=82, method=6)
            time.sleep(0.1)
        except Exception as ex:
            print(f"  ! photo {code}: {ex}")
            return None
    credit = info["artist"] or "Wikimedia Commons"
    if info["license"]:
        credit += f" · {info['license']}"
    return {"photo": f"assets/politicians/dun/{slug}.webp", "credit": credit}


def current_holders():
    """seat code -> (official name, state name)."""
    seats = {s["code"]: s for s in json.load(open(SEATS))["seats"]}
    holders = {}
    rd = json.load(open(RESULTS))
    for code, v in rd.items():
        if v.get("name"):
            holders[code] = (v["name"], v["state"])
    prn = json.load(open(PRN16))
    for code, e in prn["seats"].items():
        if e.get("incumbent_2022") and code in seats:
            holders[code] = (e["incumbent_2022"], "Johor")
    return holders


def main():
    os.makedirs(CACHE, exist_ok=True)
    overrides = json.load(open(OVERRIDES)) if os.path.exists(OVERRIDES) else {}
    holders = current_holders()
    out, matched, blocked = {}, 0, 0
    total = len(holders)
    done = 0
    for code, (name, st) in sorted(holders.items()):
        done += 1
        if code in overrides:
            if overrides[code] is None:
                blocked += 1
                continue
            label, img = entity_photo(overrides[code])
            qid = overrides[code]
        else:
            qid, label, img = resolve(name, st)
        if not qid or not img:
            continue
        p = fetch_photo(code, img)
        if not p:
            continue
        rec = {"name": label or clean_name(name), "wikidata": qid, "photo": p["photo"], "photo_credit": p["credit"]}
        # official name shown as the ballot-name subtitle when it differs meaningfully
        if namekey(name) != namekey(rec["name"]):
            rec["ballot_name"] = name
        out[code] = rec
        matched += 1
        if done % 50 == 0:
            print(f"  {done}/{total} processed, {matched} photos")
    with open(OUT, "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    kb = os.path.getsize(OUT) // 1024
    print(f"ADUN portraits: {matched}/{total} seats matched"
          + (f", {blocked} blocked" if blocked else "")
          + f" -> {os.path.relpath(OUT, ROOT)} ({kb} KB)")


if __name__ == "__main__":
    main()
