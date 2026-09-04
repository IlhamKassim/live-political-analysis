#!/usr/bin/env python3
"""Bake full profile cards for every Johor PRN16 candidate.

Sources (owned / public, no fabricated bios):
  • public/data/prn16-johor.json          — SPR-confirmed field (master)
  • pipeline/raw/meco_consol_ballots.csv  — age/sex/ethnicity + election history
  • pipeline/raw/sinar_johor_candidates.json — Sinar PRU photo + profile URL
    (optional; produced by fetching undian seat pages)
  • existing public/data/politician-profiles-johor.json curated rows
    (preserved: non-empty richer fields win over auto-bake)

Doctrine:
  Empty arrays = not found. Never invent education/career/socials.
  source_quality labels honesty level.

Output: public/data/politician-profiles-johor.json
"""
from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRN = ROOT / "public" / "data" / "prn16-johor.json"
MECO = ROOT / "pipeline" / "raw" / "meco_consol_ballots.csv"
SINAR = ROOT / "pipeline" / "raw" / "sinar_johor_candidates.json"
SINAR_MATCH = ROOT / "pipeline" / "raw" / "sinar_match.json"
MECO_MATCH = ROOT / "pipeline" / "raw" / "meco_match.json"
# Hand-curated rich profiles (do NOT point at OUT — would re-merge auto-bake)
CURATED = ROOT / "pipeline" / "raw" / "profiles_curated_johor.json"
OUT = ROOT / "public" / "data" / "politician-profiles-johor.json"

MYT = timezone(timedelta(hours=8))

_TITLES = {
    "datuk", "dato", "datin", "dr", "haji", "hj", "tuan", "puan", "ir",
    "ts", "tan", "sri", "seri", "yb", "prof", "hajah", "ustaz", "yab",
    "ybhg", "capt", "kapt", "mejar", "leftenan",
}


def namekey(s: str) -> str:
    """Loose person key: drop titles / bin / binti / a-l / a-p / anak / punct."""
    toks = [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t]
    drop = _TITLES | {"bin", "binti", "b", "bt", "al", "ap", "anak", "a"}
    return "".join(t for t in toks if t not in drop)


def namekey_loose(s: str) -> str:
    return namekey(s)


def load_prn():
    return json.loads(PRN.read_text())


def load_meco_johor():
    """Index Johor MECO rows by namekey and by (ncode, namekey)."""
    by_key = defaultdict(list)
    by_seat_key = defaultdict(list)
    se16 = []
    if not MECO.exists():
        print("  WARN: MECO ballots missing — run 03_results_dun.py first")
        return by_key, by_seat_key, se16
    with MECO.open() as f:
        for r in csv.DictReader(f):
            if r.get("state") != "Johor":
                continue
            seat = r.get("seat") or ""
            ncode = seat.split(" ", 1)[0] if seat.startswith("N.") else ""
            nk = namekey(r.get("name") or r.get("name_on_ballot") or "")
            if not nk:
                continue
            row = dict(r)
            row["_ncode"] = ncode
            row["_nk"] = nk
            by_key[nk].append(row)
            if ncode:
                by_seat_key[(ncode, nk)].append(row)
            if r.get("election") == "SE-16":
                se16.append(row)
    return by_key, by_seat_key, se16


def load_sinar():
    """Sinar rows keyed by namekey + by seat slug (deduped by sinar_id)."""
    if not SINAR.exists():
        return {}, {}
    rows = json.loads(SINAR.read_text())
    by_id = {}
    for r in rows:
        sid = str(r.get("sinar_id") or "")
        if sid:
            by_id[sid] = r
        else:
            by_id[id(r)] = r
    rows = list(by_id.values())
    by_key = {}
    by_seat = defaultdict(list)
    for r in rows:
        nk = namekey(r.get("name") or r.get("slug") or "")
        if nk:
            prev = by_key.get(nk)
            if not prev or len(r.get("name") or "") > len(prev.get("name") or ""):
                by_key[nk] = r
        seat_slug = re.sub(r"[^a-z0-9]", "", (r.get("seat_path") or "").split("/")[-1].lower())
        if seat_slug:
            by_seat[seat_slug].append(r)
    return by_key, by_seat

def load_existing():
    """Hand-curated profiles only (seed file). Never read OUT — avoids auto-bake loops."""
    if not CURATED.exists():
        return {}
    data = json.loads(CURATED.read_text())
    return data.get("profiles") or {}

def load_match_tables():
    """Precomputed seat-scoped fuzzy matches (sinar_match.json / meco_match.json)."""
    sinar_m, meco_m = {}, {}
    if SINAR_MATCH.exists():
        for row in json.loads(SINAR_MATCH.read_text()):
            sinar_m[(row["seat_code"], row["candidate"])] = row
    if MECO_MATCH.exists():
        for row in json.loads(MECO_MATCH.read_text()):
            meco_m[(row["seat_code"], row["candidate"])] = row
    return sinar_m, meco_m

def match_meco_se16(candidate_name, ncode, se16_rows, by_seat_key, by_key):
    nk = namekey(candidate_name)
    tokens = _token_set(candidate_name)
    # exact seat+name first
    for r in by_seat_key.get((ncode, nk), []):
        if r.get("election") == "SE-16":
            return r
    # fuzzy same-seat SE-16
    best, best_score = None, 0
    for r in se16_rows:
        if r.get("_ncode") != ncode:
            continue
        rk = r["_nk"]
        rt = _token_set(r.get("name") or r.get("name_on_ballot") or "")
        score = 0
        if rk == nk:
            score = 100
        else:
            inter = tokens & rt
            score = len(inter)
            if len(rk) >= 6 and (rk in nk or nk in rk):
                score += 3
            for t in inter:
                if len(t) >= 5:
                    score += 1
        if score > best_score:
            best, best_score = r, score
    if best and best_score >= 2:
        return best
    # global namekey
    for r in by_key.get(nk, []):
        if r.get("election") == "SE-16":
            return r
    return None


def election_history_for(nk: str, by_key, uid: str | None, limit=8):
    rows = list(by_key.get(nk, []))
    if uid:
        for rlist in by_key.values():
            for r in rlist:
                if r.get("candidate_uid") == uid and r not in rows:
                    rows.append(r)
    # de-dupe by election+seat+date
    seen = set()
    uniq = []
    for r in rows:
        k = (r.get("election"), r.get("seat"), r.get("date"), r.get("result"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    uniq.sort(key=lambda r: r.get("date") or "", reverse=True)
    out = []
    for r in uniq[:limit]:
        elect = r.get("election") or "?"
        year = (r.get("date") or "")[:4]
        seat = r.get("seat") or ""
        party = r.get("party") or ""
        coal = r.get("coalition") or ""
        if coal in ("ALONE", "BEBAS", ""):
            coal = party
        votes = r.get("votes") or ""
        try:
            v = int(float(votes)) if votes not in ("", None) else 0
        except ValueError:
            v = 0
        pct = r.get("votes_perc") or ""
        try:
            p = float(pct) if pct not in ("", None) else None
        except ValueError:
            p = None
        result = (r.get("result") or "").strip().lower()
        if result in ("pending", ""):
            result_s = "upcoming"
        elif result.startswith("won"):
            result_s = "won"
        elif result.startswith("lost"):
            result_s = "lost"
        else:
            result_s = result
        bloc = f"{party} ({coal})" if party and coal and party != coal else (party or coal or "?")
        if result_s == "upcoming" or v <= 0:
            line = f"{elect} {year} - {seat} - {bloc} - {result_s}"
        else:
            pct_s = f" ({p:.1f}%)" if p is not None else ""
            line = f"{elect} {year} - {seat} - {bloc} - {v:,} votes{pct_s} - {result_s}"
        out.append(line)
    return out


def party_history_for(nk: str, by_key, current_party, current_coalition):
    rows = by_key.get(nk, [])
    # chronological unique party labels
    pairs = []
    seen = set()
    for r in sorted(rows, key=lambda x: x.get("date") or ""):
        party = r.get("party") or ""
        coal = r.get("coalition") or ""
        if coal in ("ALONE", ""):
            coal = party
        key = (party, coal)
        if not party or key in seen:
            continue
        seen.add(key)
        year = (r.get("date") or "")[:4]
        pairs.append({
            "period": year or "?",
            "party": party,
            "coalition": coal,
            "note": f"Contested {r.get('election') or ''} {r.get('seat') or ''}".strip(),
        })
    if not pairs and current_party:
        pairs.append({
            "period": "2026",
            "party": current_party,
            "coalition": current_coalition or current_party,
            "note": "Candidate for PRN Johor 2026",
        })
    return pairs[-6:]


def track_record_for(entry, cand, is_incumbent, meco_se16):
    items = []
    ncode = entry.get("ncode")
    seat_name = entry.get("name")
    if is_incumbent:
        items.append({
            "period": "2022–2026",
            "title": f"ADUN {ncode} {seat_name}",
            "seat": f"{ncode} {seat_name}",
            "coalition": (entry.get("incumbent_party_2022") or "").split("-")[0] or cand.get("coalition"),
            "note": "Sitting assemblyman; assembly dissolved for PRN 11 Jul 2026",
        })
        maj = entry.get("majority_2022")
        if maj:
            items.append({
                "period": "2022",
                "title": f"Won {ncode} {seat_name}",
                "note": f"Majority {maj}",
            })
    items.append({
        "period": "2026",
        "title": "State-election candidate",
        "seat": f"{ncode} {seat_name}",
        "coalition": cand.get("coalition"),
        "note": f"{cand.get('party') or cand.get('coalition')} ticket, PRN Johor 2026",
    })
    if meco_se16 and meco_se16.get("age"):
        # not track record — used in summary
        pass
    return items


def current_role(entry, cand, is_incumbent):
    ncode = entry.get("ncode")
    seat = entry.get("name")
    coal = cand.get("coalition") or ""
    party = cand.get("party") or coal
    if is_incumbent:
        # special case MB known from curated data elsewhere
        return f"Incumbent ADUN {ncode} {seat}; contesting PRN Johor 2026 for {coal} ({party})"
    return f"{coal} candidate ({party}) for {ncode} {seat}, PRN Johor 2026"


def summary_for(entry, cand, is_incumbent, meco_se16, sinar):
    bits = []
    name = cand.get("name")
    ncode = entry.get("ncode")
    seat = entry.get("name")
    coal = cand.get("coalition") or ""
    party = cand.get("party") or coal
    alias = cand.get("ballot_name")
    if alias and namekey(alias) != namekey(name):
        bits.append(f"{name} (ballot name: {alias})")
    else:
        bits.append(name)
    bits.append(
        f"is the {coal} candidate from {party} for {ncode} {seat} in the Johor state election (PRN 16, polling 11 Jul 2026)."
    )
    if is_incumbent:
        bits.append(
            f"They are the sitting ADUN (2022 incumbent: {entry.get('incumbent_party_2022') or 'n/a'}"
            + (f", majority {entry.get('majority_2022')}" if entry.get("majority_2022") else "")
            + ")."
        )
    if meco_se16:
        age = meco_se16.get("age")
        sex = meco_se16.get("sex")
        eth = meco_se16.get("ethnicity")
        demo = []
        if age:
            demo.append(f"age {age}")
        if sex:
            demo.append({"M": "male", "F": "female"}.get(sex, sex))
        if eth:
            demo.append(eth)
        if demo:
            bits.append("MECO lists them as " + ", ".join(demo) + ".")
    if sinar:
        bits.append("Sinar Harian PRU publishes a candidate page for this contest.")
    return " ".join(bits)


def sources_for(entry, cand, meco_se16, sinar, curated_sources):
    src = []
    seen = set()

    def add(label, url):
        if not url or url in seen:
            return
        seen.add(url)
        src.append({"label": label, "url": url})

    if sinar and sinar.get("profile_url"):
        add("Sinar PRU profile", sinar["profile_url"])
    if meco_se16 and meco_se16.get("candidate_uid"):
        uid = meco_se16["candidate_uid"]
        add("ElectionData.MY", f"https://electiondata.my/candidates/{uid}")
    add(
        "SPR-confirmed nomination list (MyPolitik bake)",
        "https://staging.mypolitik.krackeddevs.com/#dun/parti/s%3AJohor/prn",
    )
    # keep curated extras
    for s in curated_sources or []:
        if isinstance(s, dict):
            add(s.get("label") or "Source", s.get("url") or "")
        elif isinstance(s, str) and s.startswith("http"):
            add("Source", s)
    return src


def merge_profile(auto: dict, curated: dict | None) -> dict:
    """Curated non-empty fields override auto; arrays prefer longer curated."""
    if not curated:
        return auto
    out = dict(auto)
    for k, v in curated.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if k in ("summary", "current_role", "photo_url", "source_quality") and v:
            out[k] = v
        elif k in (
            "party_history", "track_record", "career_highlights",
            "education", "election_history", "social_links", "sources",
        ):
            if isinstance(v, list) and len(v) >= len(out.get(k) or []):
                out[k] = v
        elif k == "official_contact" and isinstance(v, dict):
            if any(v.values()):
                out[k] = v
        elif k not in out or not out[k]:
            out[k] = v
    # quality: bump if curated was rich
    cq = str(curated.get("source_quality") or "")
    if "encyclopedia" in cq or "official" in cq or "profile +" in cq:
        out["source_quality"] = cq
    elif curated.get("summary") and len(curated.get("summary") or "") > 120:
        if out.get("source_quality") == "auto":
            out["source_quality"] = "profile + auto"
    return out


def _token_set(s: str) -> set[str]:
    toks = [t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t and len(t) > 1]
    drop = _TITLES | {"bin", "binti", "b", "bt", "al", "ap", "anak", "a"}
    return {t for t in toks if t not in drop}


def find_sinar(cand_name, seat_name, sinar_by_key, sinar_by_seat):
    """Prefer same-seat fuzzy match (Sinar names are ALL-CAPS / spelling variants)."""
    nk = namekey(cand_name)
    tokens = _token_set(cand_name)
    slug = re.sub(r"[^a-z0-9]", "", (seat_name or "").lower())
    pool = list(sinar_by_seat.get(slug, []))
    # 1) exact namekey on same seat
    for r in pool:
        if namekey(r.get("name") or "") == nk:
            return r
    # 2) token overlap on same seat (need ≥2 shared tokens or one long unique)
    best, best_score = None, 0
    for r in pool:
        rk = namekey(r.get("name") or "")
        rt = _token_set(r.get("name") or "")
        if not rt:
            continue
        inter = tokens & rt
        score = len(inter)
        # bonus if long containment
        if len(rk) >= 6 and (rk in nk or nk in rk):
            score += 2
        # distinctive long tokens
        for t in inter:
            if len(t) >= 6:
                score += 1
        if score > best_score:
            best, best_score = r, score
    if best and best_score >= 2:
        return best
    # 3) global exact
    if nk in sinar_by_key:
        return sinar_by_key[nk]
    # 4) global loose containment
    for rk, r in sinar_by_key.items():
        if len(rk) >= 7 and (rk in nk or nk in rk):
            return r
    return None

def find_curated(seat_code, cand_name, existing):
    by_seat = existing.get(seat_code) or {}
    if cand_name in by_seat:
        return by_seat[cand_name]
    nk = namekey(cand_name)
    for name, prof in by_seat.items():
        pk = namekey(name)
        if pk == nk or (len(pk) >= 6 and (pk in nk or nk in pk)):
            return prof
    return None


def photo_url_ok_guess(sinar):
    if not sinar:
        return ""
    return sinar.get("photo_url") or ""


def build():
    print("12_johor_profiles: baking profiles for all Johor PRN candidates")
    prn = load_prn()
    by_key, by_seat_key, se16 = load_meco_johor()
    sinar_by_key, sinar_by_seat = load_sinar()
    sinar_match, meco_match = load_match_tables()
    existing = load_existing()
    print(f"  PRN seats={len(prn.get('seats') or {})}  MECO SE-16={len(se16)}  "
          f"Sinar rows={len(sinar_by_key)}  match tables sinar={len(sinar_match)} "
          f"meco={len(meco_match)}  curated seats={len(existing)}")

    profiles = {}
    stats = {
        "candidates": 0,
        "with_meco": 0,
        "with_sinar": 0,
        "with_photo": 0,
        "with_history": 0,
        "incumbents": 0,
        "curated_merged": 0,
    }

    for code, entry in sorted((prn.get("seats") or {}).items()):
        ncode = entry.get("ncode") or ""
        seat_name = entry.get("name") or ""
        seat_profiles = {}
        inc_key = namekey(entry.get("incumbent_2022") or "")
        for cand in entry.get("candidates") or []:
            stats["candidates"] += 1
            cname = cand.get("name") or ""
            is_inc = bool(inc_key and namekey(cname) == inc_key)
            if is_inc:
                stats["incumbents"] += 1

            # prefer precomputed seat-scoped match tables
            mm = meco_match.get((code, cname))
            if mm:
                # reconstruct a meco-like row for history lookup
                meco = {
                    "age": mm.get("age"),
                    "sex": mm.get("sex"),
                    "ethnicity": mm.get("ethnicity"),
                    "candidate_uid": mm.get("candidate_uid"),
                    "name": mm.get("name"),
                    "name_on_ballot": mm.get("name_on_ballot"),
                    "election": "SE-16",
                    "_nk": namekey(mm.get("name") or cname),
                    "_ncode": ncode,
                }
            else:
                meco = match_meco_se16(cname, ncode, se16, by_seat_key, by_key)
            if meco:
                stats["with_meco"] += 1

            sm = sinar_match.get((code, cname))
            if sm:
                sinar = {
                    "sinar_id": sm.get("sinar_id"),
                    "slug": sm.get("slug"),
                    "name": sm.get("sinar_name") or sm.get("name"),
                    "photo_url": sm.get("photo_url"),
                    "photo_verified": bool(sm.get("photo_verified") or sm.get("photo_url")),
                    "profile_url": sm.get("profile_url"),
                    "aka": sm.get("aka"),
                    "education": sm.get("education") or [],
                    "career": sm.get("career") or [],
                    "sinar_summary": sm.get("sinar_summary"),
                    "seat_path": sm.get("seat_path"),
                }
            else:
                sinar = find_sinar(cname, seat_name, sinar_by_key, sinar_by_seat)
            if sinar:
                stats["with_sinar"] += 1
            curated = find_curated(code, cname, existing)
            if curated:
                stats["curated_merged"] += 1

            nk = namekey(cname)
            # prefer MECO official name key for history when available
            hist_key = namekey((meco or {}).get("name") or cname)
            uid = (meco or {}).get("candidate_uid")
            hist = election_history_for(hist_key, by_key, uid)
            if not hist:
                hist = election_history_for(nk, by_key, uid)
            if hist:
                stats["with_history"] += 1
            # verified Sinar photo only (guessed undian URLs often return HTML 200)
            photo = ""
            if sinar and sinar.get("photo_verified") and sinar.get("photo_url"):
                photo = sinar["photo_url"]
                stats["with_photo"] += 1
            elif curated and curated.get("photo_url"):
                photo = curated["photo_url"]
                stats["with_photo"] += 1

            quality = "auto"
            if sinar and meco:
                quality = "sinar + meco"
            elif sinar:
                quality = "sinar"
            elif meco:
                quality = "meco"
            if curated and (curated.get("career_highlights") or curated.get("education")):
                quality = curated.get("source_quality") or "profile + auto"

            sinar_edu = list((sinar or {}).get("education") or [])
            sinar_career = list((sinar or {}).get("career") or [])
            sinar_summary = (sinar or {}).get("sinar_summary") or ""
            aka = (sinar or {}).get("aka") or ""

            summary = summary_for(entry, cand, is_inc, meco, sinar)
            if sinar_summary and len(sinar_summary) > len(summary):
                summary = sinar_summary
            if aka and aka.lower() not in summary.lower():
                summary = f"{cname} (also known as {aka}). " + summary

            auto = {
                "name": cname,
                "party": cand.get("party") or "",
                "coalition": cand.get("coalition") or "",
                "seat_code": code,
                "seat_name": seat_name,
                "ncode": ncode,
                "state": "Johor",
                "ballot_name": cand.get("ballot_name") or aka or "",
                "symbol": cand.get("symbol") or "",
                "photo_url": photo,
                "current_role": current_role(entry, cand, is_inc),
                "summary": summary,
                "party_history": party_history_for(
                    nk, by_key, cand.get("party"), cand.get("coalition")
                ),
                "track_record": track_record_for(entry, cand, is_inc, meco),
                "career_highlights": sinar_career,
                "education": sinar_edu,
                "election_history": hist,
                "demographics": {
                    "age": (meco or {}).get("age") or None,
                    "sex": (meco or {}).get("sex") or None,
                    "ethnicity": (meco or {}).get("ethnicity") or None,
                },
                "meco_candidate_uid": uid or None,
                "sinar_id": (sinar or {}).get("sinar_id"),
                "is_incumbent_2022": is_inc,
                "official_contact": {
                    "address": "",
                    "phone": "",
                    "fax": "",
                    "email": "",
                },
                "social_links": [],
                "sources": sources_for(
                    entry, cand, meco, sinar,
                    (curated or {}).get("sources"),
                ),
                "source_quality": quality,
            }
            seat_profiles[cname] = merge_profile(auto, curated)
        profiles[code] = seat_profiles

    out = {
        "generated_at": datetime.now(MYT).strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "method": (
            "Auto-bake for all 172 Johor PRN16 candidates from SPR nomination list "
            "(prn16-johor.json) + Malaysian Election Corpus (age/sex/ethnicity, "
            "election history) + optional Sinar Harian PRU undian pages (photo + "
            "profile URL). Curated hand-profiles are merged on top. Empty arrays "
            "mean the field was not found — nothing is fabricated."
        ),
        "stats": stats,
        "profiles": profiles,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"  wrote {OUT.relative_to(ROOT)}")
    print(f"  stats: {json.dumps(stats)}")
    return stats


if __name__ == "__main__":
    build()
