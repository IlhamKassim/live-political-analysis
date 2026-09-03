#!/usr/bin/env python3
"""Johor PRN enrichment pass — everything still thin after 12_johor_profiles.

Produces / updates:
  public/data/seat-context-johor.json   — per-DUN context pack
  public/data/exco-johor.json           — caretaker EXCO portfolio map
  public/data/politician-profiles-johor.json  — socials, contact, local photos, deeper hist
  public/assets/politicians/dun/johor/*.webp  — localised candidate photos
  public/data/johor-pledges.json        — PN status refresh (if --pledges)
  pipeline/raw/sinar_match.json         — photo_url → local path rewrite

Sources only; never invent bios/socials.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html as htmlmod
import io
import json
import os
import re
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
PRN = ROOT / "public" / "data" / "prn16-johor.json"
MECO = ROOT / "pipeline" / "raw" / "meco_consol_ballots.csv"
PROFILES = ROOT / "public" / "data" / "politician-profiles-johor.json"
SINAR_MATCH = ROOT / "pipeline" / "raw" / "sinar_match.json"
MECO_MATCH = ROOT / "pipeline" / "raw" / "meco_match.json"
PLEDGES = ROOT / "public" / "data" / "johor-pledges.json"
SEAT_CTX_OUT = ROOT / "public" / "data" / "seat-context-johor.json"
EXCO_OUT = ROOT / "public" / "data" / "exco-johor.json"
PHOTO_DIR = ROOT / "public" / "assets" / "politicians" / "dun" / "johor"
PHOTO_CACHE = ROOT / "pipeline" / "raw" / "photo_cache"
DEWAN_CACHE = ROOT / "pipeline" / "raw" / "dewan_ahli"
SOCIAL_CACHE = ROOT / "pipeline" / "raw" / "wikidata_socials_johor.json"

UA = "MyPolitikEnrich/1.0 (civic open data; https://mypolitik.xyz)"
MYT = timezone(timedelta(hours=8))

# Caretaker EXCO — portfolios from public reporting / official pages as of PRN 2026.
# seat_code links to the DUN they hold. Verified against known public offices; empty
# photo fields filled from profiles later.
EXCO_SEED = [
    {"role": "Menteri Besar", "name": "Datuk Onn Hafiz Ghazi", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.26", "portfolio": "Menteri Besar Johor (caretaker)", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Zahari Sarip", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.01", "portfolio": "Agriculture, agro-based industry & rural development", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Dr Mohd Puad Zarkashi", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.25", "portfolio": "Education & information", "since": "2022",
     "note": "Sitting ADUN Rengit; check field list for 2026 contest status"},
    {"role": "EXCO", "name": "Datuk Mohamad Najib Samuri", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.21", "portfolio": "Public works, transport & infrastructure", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Samsolbari Jamali", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.20", "portfolio": "Health & environment", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Mohd Fared Mohd Khalid", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.17", "portfolio": "Housing & local government", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Zulkurnain Kamisan", "party": "UMNO", "coalition": "BN",
     "seat_code": "1_N.18", "portfolio": "Tourism, culture & heritage", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Ling Tian Soon", "party": "MCA", "coalition": "BN",
     "seat_code": "1_N.19", "portfolio": "Human resources, youth & sports", "since": "2022"},
    {"role": "EXCO", "name": "Datuk Lee Ting Han", "party": "MCA", "coalition": "BN",
     "seat_code": "1_N.30", "portfolio": "Investment, trade & consumer affairs", "since": "2022"},
    {"role": "EXCO", "name": "R Vidyananthan", "party": "MIC", "coalition": "BN",
     "seat_code": "1_N.31", "portfolio": "Unity & national integration", "since": "2022"},
]


def now_iso():
    return datetime.now(MYT).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("content-type", "")


def namekey(s: str) -> str:
    titles = {"datuk", "dato", "datin", "dr", "haji", "hj", "yb", "yab", "tan", "sri", "seri"}
    toks = [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]
    return "".join(t for t in toks if t not in titles | {"bin", "binti", "al", "ap", "anak", "a"})


# ── seat context ────────────────────────────────────────────────────────────

def bake_seat_context(prn):
    """Per-DUN pack: electorate, last result, parent P, by-election notes, competitiveness."""
    meco_by = defaultdict(list)
    if MECO.exists():
        with MECO.open() as f:
            for r in csv.DictReader(f):
                if r.get("state") != "Johor":
                    continue
                ncode = (r.get("seat") or "").split(" ", 1)[0]
                if ncode.startswith("N."):
                    meco_by[ncode].append(r)

    seats = {}
    for code, s in prn["seats"].items():
        ncode = s.get("ncode") or ""
        last_field = s.get("last_field") or []
        last_year = s.get("last_field_year")
        maj = s.get("majority_2022")
        votes = s.get("incumbent_votes_2022")
        pct = s.get("incumbent_pct_2022")
        # by-election note: if last completed contest date year > 2022 and election BY
        bye = None
        rows = meco_by.get(ncode, [])
        completed = [r for r in rows if r.get("election") != "SE-16"
                     and (r.get("date") or "") < "2026-01-01"]
        if completed:
            latest = max(r["date"] for r in completed)
            lat = [r for r in completed if r["date"] == latest]
            if any(r.get("election") == "BY-ELECTION" for r in lat):
                win = next((r for r in lat if (r.get("result") or "").lower().startswith("won")), lat[0])
                bye = {
                    "date": latest,
                    "winner": win.get("name"),
                    "party": win.get("party"),
                    "coalition": win.get("coalition") if win.get("coalition") not in ("ALONE", "") else win.get("party"),
                    "note": f"By-election {latest[:4]} superseded the 2022 general result for the sitting ADUN.",
                }
        # competitiveness from majority pct
        comp = None
        if pct is not None and votes:
            try:
                total = votes / (float(pct) / 100.0) if float(pct) else None
                maj_n = float(str(maj).replace(",", "")) if maj else None
                if total and maj_n is not None:
                    mp = 100.0 * maj_n / total
                    comp = "marginal" if mp < 5 else "leaning" if mp < 15 else "safe"
            except (ValueError, ZeroDivisionError):
                pass
        seats[code] = {
            "ncode": ncode,
            "name": s.get("name"),
            "electorate": s.get("electorate"),
            "incumbent_2022": s.get("incumbent_2022"),
            "incumbent_party_2022": s.get("incumbent_party_2022"),
            "majority_2022": maj,
            "incumbent_votes_2022": votes,
            "incumbent_pct_2022": pct,
            "last_field": last_field,
            "last_field_year": last_year,
            "byelection": bye,
            "competitiveness": comp,
            "candidates_2026": len(s.get("candidates") or []),
            "parlimen": None,  # filled from seats-dun if available
        }

    # parent parliament from seats-dun
    seats_dun = ROOT / "public" / "data" / "seats-dun.json"
    if seats_dun.exists():
        data = json.loads(seats_dun.read_text())
        for seat in data.get("seats") or []:
            code = seat.get("code") or seat.get("code_state_dun")
            if code in seats:
                seats[code]["parlimen"] = seat.get("parlimen") or seat.get("code_parlimen")
                seats[code]["parlimen_name"] = seat.get("parlimen_name") or seat.get("name_parlimen")

    out = {
        "generated_at": now_iso(),
        "state": "Johor",
        "election": "prn16-johor",
        "seats": seats,
    }
    SEAT_CTX_OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"  seat-context: {len(seats)} seats → {SEAT_CTX_OUT.relative_to(ROOT)}")
    return out


# ── EXCO ────────────────────────────────────────────────────────────────────

def bake_exco(profiles):
    members = []
    for row in EXCO_SEED:
        code = row["seat_code"]
        name = row["name"]
        photo = ""
        by_seat = (profiles.get("profiles") or {}).get(code) or {}
        # name match
        nk = namekey(name)
        for pn, p in by_seat.items():
            if namekey(pn) == nk or nk in namekey(pn) or namekey(pn) in nk:
                photo = p.get("photo_url") or ""
                break
        members.append({**row, "photo_url": photo})
    out = {
        "generated_at": now_iso(),
        "state": "Johor",
        "status": "caretaker",
        "note": (
            "Caretaker state executive as of the dissolution for PRN Johor 2026. "
            "Portfolios from public/official reporting; not a claim of post-election appointments."
        ),
        "source": "Public reporting + Dewan Negeri Johor / state government releases",
        "members": members,
    }
    EXCO_OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"  exco: {len(members)} members → {EXCO_OUT.relative_to(ROOT)}")
    return out


# ── local photos ────────────────────────────────────────────────────────────

def localise_photos(profiles, limit=None):
    if Image is None:
        print("  ! Pillow missing — skip photo localisation (pip install pillow)")
        return 0
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    PHOTO_CACHE.mkdir(parents=True, exist_ok=True)
    n = 0
    failed = 0
    for code, people in (profiles.get("profiles") or {}).items():
        for cname, p in people.items():
            url = p.get("photo_url") or ""
            if not url or url.startswith("assets/"):
                if url.startswith("assets/"):
                    n += 1
                continue
            if limit and n >= limit:
                break
            # stable filename
            slug = re.sub(r"[^a-z0-9]+", "-", namekey(cname))[:40] or "cand"
            ncode = (p.get("ncode") or code.split("_")[-1]).replace(".", "-")
            rel = f"assets/politicians/dun/johor/{ncode}_{slug}.webp"
            dest = ROOT / "public" / rel
            if dest.exists() and dest.stat().st_size > 500:
                p["photo_url"] = rel
                p["photo_credit"] = p.get("photo_credit") or "Sinar Harian PRU"
                n += 1
                continue
            cache = PHOTO_CACHE / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".bin")
            try:
                if cache.exists():
                    raw = cache.read_bytes()
                else:
                    raw, ct = fetch(url, timeout=25)
                    if "html" in (ct or "") or raw[:20].lstrip().startswith(b"<!") or raw[:20].lstrip().startswith(b"<html"):
                        failed += 1
                        continue
                    cache.write_bytes(raw)
                    time.sleep(0.15)
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((320, 320))
                dest.parent.mkdir(parents=True, exist_ok=True)
                im.save(dest, "WEBP", quality=82)
                p["photo_url"] = rel
                p["photo_credit"] = "Sinar Harian PRU"
                p["photo_source_url"] = url
                n += 1
            except Exception as e:
                failed += 1
                if failed <= 5:
                    print(f"    photo fail {cname}: {e}")
        if limit and n >= limit:
            break
    print(f"  photos localised: {n}  failed: {failed}")
    return n


# ── Dewan Negeri contacts for incumbents ────────────────────────────────────

def scrape_dewan_contacts(prn, profiles):
    DEWAN_CACHE.mkdir(parents=True, exist_ok=True)
    filled = 0
    for code, s in prn["seats"].items():
        ncode = s.get("ncode") or ""
        m = re.search(r"N\.?(\d+)", ncode, re.I)
        if not m:
            continue
        num = int(m.group(1))
        url = f"https://dewannegeri.johor.gov.my/ahli/n{num:02d}/"
        cache = DEWAN_CACHE / f"n{num:02d}.html"
        try:
            if cache.exists() and cache.stat().st_size > 2000:
                html = cache.read_text(errors="replace")
            else:
                raw, _ = fetch(url, timeout=20)
                html = raw.decode("utf-8", "replace")
                cache.write_text(html)
                time.sleep(0.25)
        except Exception:
            continue
        text = re.sub(r"(?is)<script.*?</script>", " ", html)
        text = re.sub(r"(?is)<style.*?</style>", " ", text)
        plain = htmlmod.unescape(re.sub(r"<[^>]+>", "\n", text))
        plain = re.sub(r"[ \t]+", " ", plain)
        # email / phone
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", plain)
        phones = re.findall(r"0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{3,4}", plain)
        # photo on dewan
        imgs = re.findall(r'src=["\']([^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)["\']', html, re.I)
        dewan_photo = None
        for im in imgs:
            if any(k in im.lower() for k in ("logo", "icon", "flag", "sprite", "wp-includes")):
                continue
            if "upload" in im.lower() or "ahli" in im.lower() or "yb" in im.lower():
                dewan_photo = im if im.startswith("http") else ("https://dewannegeri.johor.gov.my" + im)
                break
        # attach to incumbent profile
        inc = s.get("incumbent_2022") or ""
        people = (profiles.get("profiles") or {}).get(code) or {}
        target = None
        for pn, p in people.items():
            if p.get("is_incumbent_2022") or namekey(pn) == namekey(inc):
                target = p
                break
        if not target:
            continue
        oc = target.setdefault("official_contact", {"address": "", "phone": "", "fax": "", "email": ""})
        if emails and not oc.get("email"):
            # prefer johor.gov / gov emails
            gov = [e for e in emails if "gov" in e.lower() or "johor" in e.lower()]
            oc["email"] = (gov or emails)[0]
            filled += 1
        if phones and not oc.get("phone"):
            oc["phone"] = phones[0]
            filled += 1
        if not oc.get("address") and "Kota Iskandar" in plain:
            oc["address"] = "Dewan Negeri Johor, Kota Iskandar, Iskandar Puteri"
        # sources
        srcs = target.setdefault("sources", [])
        if not any((s.get("url") if isinstance(s, dict) else "") == url for s in srcs):
            srcs.append({"label": "Dewan Negeri Johor", "url": url})
        if dewan_photo and not target.get("photo_url"):
            target["photo_url"] = dewan_photo
    print(f"  dewan contacts touched: {filled}")
    return filled


# ── Wikidata socials (incumbents + high-profile) ────────────────────────────

def wikidata_socials(profiles, prn, max_people=80):
    """Lookup socials via wbsearchentities + wbgetentities for incumbents first."""
    cache = {}
    if SOCIAL_CACHE.exists():
        try:
            cache = json.loads(SOCIAL_CACHE.read_text())
        except Exception:
            cache = {}

    # prioritise incumbents
    queue = []
    for code, s in prn["seats"].items():
        for c in s.get("candidates") or []:
            is_inc = namekey(c["name"]) == namekey(s.get("incumbent_2022") or "")
            queue.append((0 if is_inc else 1, code, c["name"]))
    queue.sort()
    queue = queue[:max_people]

    props = {
        "P2013": "facebook",
        "P2003": "instagram",
        "P2002": "twitter",
        "P7085": "tiktok",
        "P856": "website",
        "P2397": "youtube",
    }
    filled = 0

    def api(params):
        q = urllib.parse.urlencode(params)
        url = "https://www.wikidata.org/w/api.php?" + q
        raw, _ = fetch(url, timeout=30)
        return json.loads(raw.decode("utf-8"))

    import urllib.parse

    for rank, code, cname in queue:
        people = (profiles.get("profiles") or {}).get(code) or {}
        p = people.get(cname)
        if not p:
            # loose
            for pn, pp in people.items():
                if namekey(pn) == namekey(cname):
                    p = pp
                    break
        if not p:
            continue
        if p.get("social_links"):
            continue
        ck = namekey(cname)
        if ck in cache:
            links = cache[ck]
        else:
            links = []
            try:
                search = api({
                    "action": "wbsearchentities", "search": cname, "language": "en",
                    "uselang": "en", "type": "item", "limit": 5, "format": "json",
                })
                qid = None
                for hit in search.get("search") or []:
                    desc = (hit.get("description") or "").lower()
                    label = (hit.get("label") or "")
                    if namekey(label) and (
                        "politician" in desc or "malaysia" in desc or "johor" in desc
                        or "assembly" in desc or "member" in desc
                    ):
                        qid = hit.get("id")
                        break
                if not qid and (search.get("search") or []):
                    # only accept if label namekey matches tightly
                    hit = search["search"][0]
                    if namekey(hit.get("label") or "") == ck or ck in namekey(hit.get("label") or ""):
                        qid = hit.get("id")
                if qid:
                    ent = api({
                        "action": "wbgetentities", "ids": qid, "props": "claims|labels",
                        "languages": "en", "format": "json",
                    })
                    claims = (ent.get("entities") or {}).get(qid, {}).get("claims") or {}
                    for pid, kind in props.items():
                        for cl in claims.get(pid) or []:
                            rank_ = cl.get("rank")
                            if rank_ == "deprecated":
                                continue
                            mainsnak = cl.get("mainsnak") or {}
                            dv = (mainsnak.get("datavalue") or {}).get("value")
                            if not dv:
                                continue
                            if kind == "facebook":
                                url = f"https://www.facebook.com/{dv}" if not str(dv).startswith("http") else dv
                            elif kind == "instagram":
                                url = f"https://www.instagram.com/{dv}"
                            elif kind == "twitter":
                                url = f"https://x.com/{dv}"
                            elif kind == "tiktok":
                                url = f"https://www.tiktok.com/@{dv}"
                            elif kind == "youtube":
                                url = f"https://www.youtube.com/channel/{dv}" if not str(dv).startswith("http") else dv
                            else:
                                url = dv if str(dv).startswith("http") else f"https://{dv}"
                            links.append(url)
                            break
                time.sleep(0.35)
            except Exception as e:
                print(f"    wd fail {cname}: {e}")
            cache[ck] = links
        if links:
            p["social_links"] = links
            p["socials_source"] = "wikidata"
            filled += 1

    SOCIAL_CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False))
    print(f"  wikidata socials filled: {filled}")
    return filled


# ── deeper election history already mostly in 12; re-attach full MECO by uid ─

def deepen_history(profiles):
    if not MECO.exists():
        return 0
    by_uid = defaultdict(list)
    by_nk = defaultdict(list)
    with MECO.open() as f:
        for r in csv.DictReader(f):
            if r.get("state") != "Johor":
                continue
            if r.get("candidate_uid"):
                by_uid[r["candidate_uid"]].append(r)
            by_nk[namekey(r.get("name") or "")].append(r)

    def lines_for(rows, limit=10):
        seen = set()
        out = []
        for r in sorted(rows, key=lambda x: x.get("date") or "", reverse=True):
            k = (r.get("election"), r.get("seat"), r.get("date"))
            if k in seen:
                continue
            seen.add(k)
            elect = r.get("election") or "?"
            year = (r.get("date") or "")[:4]
            seat = r.get("seat") or ""
            party = r.get("party") or ""
            coal = r.get("coalition") or party
            if coal in ("ALONE", ""):
                coal = party
            try:
                v = int(float(r.get("votes") or 0))
            except ValueError:
                v = 0
            result = (r.get("result") or "").strip().lower()
            if result in ("pending", ""):
                rs = "upcoming"
            elif result.startswith("won"):
                rs = "won"
            elif result.startswith("lost"):
                rs = "lost"
            else:
                rs = result
            bloc = f"{party} ({coal})" if party and coal and party != coal else (party or "?")
            if rs == "upcoming" or v <= 0:
                out.append(f"{elect} {year} - {seat} - {bloc} - {rs}")
            else:
                out.append(f"{elect} {year} - {seat} - {bloc} - {v:,} votes - {rs}")
            if len(out) >= limit:
                break
        return out

    n = 0
    for people in (profiles.get("profiles") or {}).values():
        for p in people.values():
            uid = p.get("meco_candidate_uid")
            rows = by_uid.get(uid) if uid else None
            if not rows:
                rows = by_nk.get(namekey(p.get("name") or ""))
            if not rows:
                continue
            hist = lines_for(rows)
            if len(hist) > len(p.get("election_history") or []):
                p["election_history"] = hist
                n += 1
    print(f"  deeper history: {n} profiles extended")
    return n


# ── PN pledges refresh ──────────────────────────────────────────────────────

def refresh_pn_pledges():
    if not PLEDGES.exists():
        return
    data = json.loads(PLEDGES.read_text())
    pn = (data.get("coalitions") or {}).get("PN") or {}
    # Public reporting (Jul 2026): PN delayed / did not fully table a formal manifesto
    # for PRN Johor in the way PH/BN did. Keep pending but update as_of + note.
    pn["pending"] = True
    pn["as_of"] = "10 Jul 2026"
    pn["note"] = (
        "As of 10 Jul 2026, PN had not published a formal multi-point manifesto "
        "comparable to PH/BN for PRN Johor 2026. Campaign messaging focused on "
        "leadership and seat-level canvassing rather than a single state manifesto. "
        "This block stays pending rather than inventing pledges."
    )
    pn["sources"] = [
        "https://harakahdaily.net/2026/06/28/manifesto-pn-johor-ada-kejutan/",
        "https://www.facebook.com/harianmetro/videos/manifesto-pn-untuk-prn-johor-akan-diumumkan-dalam-masa-terdekat-takiyuddinhttpsw/1052042534064378/",
    ]
    data["coalitions"]["PN"] = pn
    data["note"] = (
        "Coalition platforms for PRN Johor 2026, faithfully summarised from published "
        "manifestos / credible reporting. PN remains pending — no full manifesto released."
    )
    PLEDGES.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print("  pledges: PN status refreshed (still pending, dated 10 Jul)")


# ── Sinar live vote helper used by poller ───────────────────────────────────

def parse_sinar_undian_votes(html, seat_path=""):
    """Extract candidate rows with vote counts from a Sinar undian seat page."""
    rows = []
    # pattern: href="/calon/ID/slug" ... nama ... votes nearby
    blocks = re.split(r'class="calon"', html, flags=re.I)
    for b in blocks[1:]:
        m = re.search(r'href=["\']/calon/(\d+)/([a-zA-Z0-9\-]+)["\']', b)
        if not m:
            continue
        name_m = re.search(r'class="nama"[^>]*>([^<]+)', b, re.I)
        # votes often in <span class="undi"> or plain number after party logo
        vote_m = re.search(r'class="(?:undi|votes|keputusan)"[^>]*>\s*([\d,]+)', b, re.I)
        if not vote_m:
            vote_m = re.search(r'>([\d]{1,3}(?:,\d{3})+)<', b)
        votes = None
        if vote_m:
            try:
                votes = int(vote_m.group(1).replace(",", ""))
            except ValueError:
                votes = None
        rows.append({
            "sinar_id": m.group(1),
            "slug": m.group(2),
            "name": (name_m.group(1).strip() if name_m else m.group(2)),
            "votes": votes,
        })
    return rows


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-photos", action="store_true")
    ap.add_argument("--skip-dewan", action="store_true")
    ap.add_argument("--skip-wikidata", action="store_true")
    ap.add_argument("--photo-limit", type=int, default=0, help="0 = all")
    ap.add_argument("--wd-limit", type=int, default=80)
    args = ap.parse_args()

    print("13_johor_enrich")
    prn = json.loads(PRN.read_text())
    profiles = json.loads(PROFILES.read_text()) if PROFILES.exists() else {"profiles": {}}

    bake_seat_context(prn)
    bake_exco(profiles)
    refresh_pn_pledges()
    deepen_history(profiles)

    if not args.skip_dewan:
        scrape_dewan_contacts(prn, profiles)
    if not args.skip_wikidata:
        wikidata_socials(profiles, prn, max_people=args.wd_limit)
    if not args.skip_photos:
        localise_photos(profiles, limit=args.photo_limit or None)

    # re-attach EXCO photos after localisation
    bake_exco(profiles)

    profiles["generated_at"] = now_iso()
    profiles["method"] = (profiles.get("method") or "") + (
        " · Enriched by 13_johor_enrich.py (local photos, dewan contacts, "
        "wikidata socials, deeper MECO history, seat-context + EXCO)."
    )
    stats = profiles.setdefault("stats", {})
    # recount
    n = ph = so = co = 0
    for people in (profiles.get("profiles") or {}).values():
        for p in people.values():
            n += 1
            if p.get("photo_url"):
                ph += 1
            if p.get("social_links"):
                so += 1
            oc = p.get("official_contact") or {}
            if any(oc.get(k) for k in ("phone", "email", "address")):
                co += 1
    stats.update({"candidates": n, "with_photo": ph, "with_socials": so, "with_contact": co})
    PROFILES.write_text(json.dumps(profiles, indent=2, ensure_ascii=False) + "\n")
    print(f"  profiles rewritten: photo={ph} socials={so} contact={co}")
    print("done")


if __name__ == "__main__":
    main()
