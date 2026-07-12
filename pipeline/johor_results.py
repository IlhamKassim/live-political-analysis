#!/usr/bin/env python3
"""Import the official 2026 Johor state-election result published by Bernama.

Bernama labels the result as official and attributes it to SPR. The server-rendered
page contains all 56 seats and 172 candidates. This importer keeps a normalized,
reviewable source snapshot, then updates the permanent DUN results and the final
live-results document without touching the preserved 2022 fields in prn16-johor.

Refresh from the official page:
  python3 pipeline/johor_results.py --fetch

Import a previously downloaded page:
  python3 pipeline/johor_results.py --input /path/to/index.html

Rebuild from the committed normalized snapshot, or only verify existing outputs:
  python3 pipeline/johor_results.py
  python3 pipeline/johor_results.py --check
"""
import argparse
import collections
import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "pipeline")
PUBLIC_DATA = os.path.join(ROOT, "public", "data")
SOURCE_URL = "https://prn.bernama.com/johor/keputusan/official/index.php"
SNAPSHOT = os.path.join(PIPELINE, "johor_prn16_bernama.json")
PRN16 = os.path.join(PUBLIC_DATA, "prn16-johor.json")
RESULTS_DUN = os.path.join(PUBLIC_DATA, "results-dun.json")
LIVE = os.path.join(PUBLIC_DATA, "live-johor.json")
ADUNS = os.path.join(PUBLIC_DATA, "aduns.json")
UA = "MyPolitikBot/1.0 (https://mypolitik.krackeddevs.com; election data audit)"

SOURCE_PARTY_COUNTS = {
    "ASLI": 1, "BEBAS": 6, "BERSAMA": 15, "BN": 56,
    "MUDA": 4, "PH": 56, "PN": 33, "PSM": 1,
}
COALITION_FULL = {
    "BN": "Barisan Nasional",
    "PH": "Pakatan Harapan",
    "PN": "Perikatan Nasional",
    "BERSAMA": "Parti Bersama Malaysia",
    "MUDA-PSM": "MUDA-PSM",
    "OTHERS": "Others",
}
PARTY_FULL = {
    "UMNO": "United Malays National Organisation",
    "MCA": "Malaysian Chinese Association",
    "MIC": "Malaysian Indian Congress",
    "PKR": "Parti Keadilan Rakyat",
    "DAP": "Democratic Action Party",
    "AMANAH": "Parti Amanah Negara",
    "PAS": "Parti Islam Se-Malaysia",
    "BERSATU": "Parti Pribumi Bersatu Malaysia",
    "MIPP": "Malaysian Indian People's Party",
    "BERSAMA": "Parti Bersama Malaysia",
    "MUDA": "Malaysian United Democratic Alliance",
    "PSM": "Parti Sosialis Malaysia",
    "ASLI": "Parti Orang Asli Malaysia",
    "BEBAS": "Independent",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data, pretty=False):
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(value).split())


def integer(value):
    return int(clean_text(value).replace(",", ""))


def source_updated(raw):
    matches = re.findall(
        r"Terkini\s*:\s*N\.\d+.*?\|\s*(\d{1,2})\s+([A-Za-z]{3})\s+"
        r"(\d{4}),\s*(\d{1,2}):(\d{2}):(\d{2})\s*([AP]M)",
        raw,
        re.S,
    )
    if not matches:
        raise ValueError("Bernama final-declaration timestamp not found")
    months = {m: i for i, m in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )}
    stamps = []
    for day, mon, year, hour, minute, second, ampm in matches:
        hour = int(hour) % 12 + (12 if ampm == "PM" else 0)
        stamps.append(dt.datetime(
            int(year), months[mon.title()], int(day), hour, int(minute), int(second),
            tzinfo=dt.timezone(dt.timedelta(hours=8)),
        ))
    # The page prints an unofficial summary first and the official/SPR summary
    # second. Their declaration timestamps differ; retain the final declaration.
    stamp = max(stamps)
    return stamp.isoformat(timespec="seconds")


def parse_candidate(fragment):
    match = re.search(
        r'<div class="candidate-info-box(?P<winner> candidate-winner-box)?">.*?'
        r'<span class="calon-number">\s*(\d+)\s*</span>.*?'
        r'<h5[^>]*>\s*(.*?)\s*<span class="party-badge-custom"[^>]*>\s*([^<]+?)\s*</span>.*?'
        r'Jantina:\s*<strong>([^<]+)</strong>.*?Umur:\s*<strong>([^<]+)</strong>.*?'
        r'Undi / Votes:</span>\s*<span[^>]*><b>([\d,]+)</b>',
        fragment,
        re.S,
    )
    if not match:
        return None
    return {
        "source_name": clean_text(match.group(3)),
        "source_party": clean_text(match.group(4)).upper(),
        "votes": integer(match.group(7)),
        "winner": bool(match.group("winner")),
        "sex": "F" if clean_text(match.group(5)).upper() == "PEREMPUAN" else "M",
        "age": integer(match.group(6)),
    }


def match_roster_candidate(source_candidate, roster):
    party = source_candidate["source_party"]
    if party in ("BN", "PH", "PN", "BERSAMA"):
        matches = [candidate for candidate in roster if candidate.get("coalition") == party]
    else:
        matches = [candidate for candidate in roster if candidate.get("party") == party]
    if len(matches) != 1:
        raise ValueError(
            f"expected one local candidate for {party}, found {len(matches)}: {matches}"
        )
    local = matches[0]
    return {
        "name": local["name"],
        "source_name": source_candidate["source_name"],
        "party": local["party"],
        "coalition": local["coalition"],
        "source_party": party,
        "votes": source_candidate["votes"],
        "winner": source_candidate["winner"],
        "sex": source_candidate["sex"],
        "age": source_candidate["age"],
    }


def parse_official_html(raw, prn, retrieved_at=None):
    if "Keputusan RASMI" not in raw or "Sumber : SPR" not in raw:
        raise ValueError("page is not marked as Bernama official results sourced from SPR")
    anchor = raw.find("Maklumat Calon & Keputusan Penuh PRN Johor 2026")
    if anchor < 0:
        raise ValueError("official full-results section not found")
    official = raw[anchor:]
    seats = {}
    for fragment in official.split("<!-- BLOK UTAMA DUN -->")[1:]:
        header = re.search(
            r'<div class="dun-header-title">\s*<span>N(\d{2})\s*-\s*([^<]+)</span>.*?'
            r'Registered Voters</i>:\s*([\d,]+)',
            fragment,
            re.S,
        )
        if not header:
            continue
        code = f"1_N.{header.group(1)}"
        source_candidates = [
            parsed for parsed in (
                parse_candidate(part)
                for part in fragment.split("<!-- KOTAK DATA CALON 2026 -->")[1:]
            ) if parsed
        ]
        stats = re.search(
            r'<div class="stats-result-box">(.*?)</div><div class="incumbent-footer-box">',
            fragment,
            re.S,
        )
        values = re.findall(r'<strong style="font-size: 15px;">(.*?)</strong>', stats.group(1), re.S) if stats else []
        if len(values) != 4:
            raise ValueError(f"{code}: expected four result statistics, found {len(values)}")
        votes_cast_match = re.fullmatch(r"([\d,]+)\s*\(([\d.]+)%\)", clean_text(values[1]))
        if not votes_cast_match:
            raise ValueError(f"{code}: malformed votes-cast statistic {clean_text(values[1])!r}")
        local_seat = prn["seats"].get(code)
        if not local_seat:
            raise ValueError(f"{code}: no matching local Johor seat")
        candidates = [match_roster_candidate(c, local_seat["candidates"]) for c in source_candidates]
        seats[code] = {
            "ncode": f"N.{header.group(1)}",
            "name": clean_text(header.group(2)).title(),
            "electorate": integer(header.group(3)),
            "majority": integer(values[0]),
            "votes_cast": integer(votes_cast_match.group(1)),
            "turnout": float(votes_cast_match.group(2)),
            "rejected_ballots": integer(values[2]),
            "unreturned_ballots": integer(values[3]),
            "candidates": candidates,
        }

    snapshot = {
        "election": "PRN Johor 2026",
        "election_id": "prn16-johor",
        "source": "Bernama official results; source: SPR",
        "source_url": SOURCE_URL,
        "source_updated": source_updated(raw),
        "retrieved_at": retrieved_at or dt.datetime.now(
            dt.timezone(dt.timedelta(hours=8))
        ).isoformat(timespec="seconds"),
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "tally": {},
        "seats": seats,
    }
    snapshot["tally"] = dict(sorted(collections.Counter(
        next(c for c in seat["candidates"] if c["winner"])["coalition"]
        for seat in seats.values()
    ).items()))
    validate_snapshot(snapshot, prn)
    return snapshot


def validate_snapshot(snapshot, prn=None):
    seats = snapshot.get("seats") or {}
    expected_codes = {f"1_N.{number:02d}" for number in range(1, 57)}
    if set(seats) != expected_codes:
        raise ValueError(f"official seat coverage mismatch: {len(seats)}/56")
    party_counts = collections.Counter()
    winner_counts = collections.Counter()
    candidate_count = 0
    for code, seat in seats.items():
        candidates = seat.get("candidates") or []
        candidate_count += len(candidates)
        party_counts.update(c["source_party"] for c in candidates)
        winners = [c for c in candidates if c.get("winner")]
        if len(winners) != 1:
            raise ValueError(f"{code}: expected one winner, found {len(winners)}")
        ranked = sorted(candidates, key=lambda c: c["votes"], reverse=True)
        winner = winners[0]
        if not ranked or ranked[0] is not winner:
            raise ValueError(f"{code}: flagged winner does not have the most votes")
        computed_majority = winner["votes"] - ranked[1]["votes"]
        if computed_majority != seat["majority"]:
            raise ValueError(f"{code}: majority {seat['majority']} != {computed_majority}")
        accounted = sum(c["votes"] for c in candidates) + seat["rejected_ballots"] + seat["unreturned_ballots"]
        if accounted != seat["votes_cast"]:
            raise ValueError(f"{code}: ballots {accounted} != votes cast {seat['votes_cast']}")
        winner_counts[winner["coalition"]] += 1
        if prn:
            local = prn["seats"][code]
            if seat["electorate"] != local["electorate"]:
                raise ValueError(f"{code}: electorate differs from local nomination data")
            if len(candidates) != len(local["candidates"]):
                raise ValueError(f"{code}: candidate count differs from local nomination data")
    if candidate_count != 172:
        raise ValueError(f"official candidate coverage mismatch: {candidate_count}/172")
    if dict(sorted(party_counts.items())) != SOURCE_PARTY_COUNTS:
        raise ValueError(f"candidate party counts differ: {dict(party_counts)}")
    if dict(sorted(winner_counts.items())) != {"BN": 48, "PH": 8}:
        raise ValueError(f"winner tally differs: {dict(winner_counts)}")
    if snapshot.get("tally") != {"BN": 48, "PH": 8}:
        raise ValueError(f"snapshot tally differs: {snapshot.get('tally')}")


def results_rows_from_snapshot(snapshot):
    rows = {}
    for code, seat in snapshot["seats"].items():
        ranked = sorted(seat["candidates"], key=lambda candidate: candidate["votes"], reverse=True)
        winner, runner = ranked[:2]
        valid_votes = sum(candidate["votes"] for candidate in ranked)
        rows[code] = {
            "state": "Johor",
            "name": winner["name"],
            "party": winner["party"],
            "party_full": PARTY_FULL.get(winner["party"], winner["party"]),
            "coalition": winner["coalition"],
            "coalition_full": COALITION_FULL.get(winner["coalition"], winner["coalition"]),
            "votes": winner["votes"],
            "vote_pct": round(100 * winner["votes"] / valid_votes, 1),
            "majority": seat["majority"],
            "majority_pct": round(100 * seat["majority"] / valid_votes, 1),
            "turnout": seat["turnout"],
            "n_candidates": len(ranked),
            "runner_up": {"name": runner["name"], "party": runner["party"], "votes": runner["votes"]},
            "election": snapshot["election"],
            "source_url": snapshot["source_url"],
            "source_updated": snapshot["source_updated"],
        }
    return rows


def live_from_snapshot(snapshot):
    seats = {}
    for code, seat in snapshot["seats"].items():
        ranked = sorted(seat["candidates"], key=lambda candidate: candidate["votes"], reverse=True)
        winner = ranked[0]
        seats[code] = {
            "status": "official",
            "coalition": winner["coalition"],
            "party": winner["party"],
            "name": winner["name"],
            "majority": str(seat["majority"]),
            "votes": winner["votes"],
            "candidates": [
                {"name": c["name"], "votes": c["votes"], "party": c["party"], "coalition": c["coalition"]}
                for c in ranked
            ],
            "sources": ["Bernama", "SPR"],
        }
    return {
        "phase": "final",
        "updated": snapshot["source_updated"],
        "election": snapshot["election_id"],
        "source": snapshot["source"],
        "source_url": snapshot["source_url"],
        "tally": snapshot["tally"],
        "seats": seats,
    }


def name_tokens(value):
    value = re.sub(
        r"\b(datuk|dato'?|seri|dr|haji|hajah|hajjah|hj|yb|yab|ustaz|ustazah|cikgu|bin|binti|bt|a/l|a/p|anak)\b",
        " ",
        (value or "").lower(),
    )
    return {token for token in re.findall(r"[a-z0-9]+", value) if len(token) >= 4}


def same_person(left, right):
    left_key = re.sub(r"[^a-z0-9]", "", (left or "").lower())
    right_key = re.sub(r"[^a-z0-9]", "", (right or "").lower())
    return bool(left_key and right_key and (left_key == right_key or name_tokens(left) & name_tokens(right)))


def validate_outputs(snapshot):
    expected_rows = results_rows_from_snapshot(snapshot)
    results = load_json(RESULTS_DUN)
    live = load_json(LIVE)
    aduns = load_json(ADUNS)
    for code, expected in expected_rows.items():
        if results.get(code) != expected:
            raise ValueError(f"{code}: results-dun is not synchronized with Bernama snapshot")
        live_row = (live.get("seats") or {}).get(code)
        if not live_row or live_row.get("status") != "official" or live_row.get("votes") != expected["votes"]:
            raise ValueError(f"{code}: live result is not synchronized with Bernama snapshot")
        adun = aduns.get(code)
        if not adun or not same_person(adun.get("name"), expected["name"]):
            raise ValueError(f"{code}: current ADUN record does not match winner {expected['name']}")
    if live.get("phase") != "final" or live.get("tally") != {"BN": 48, "PH": 8}:
        raise ValueError("live result phase/tally is not final BN48/PH8")


def import_outputs(snapshot):
    results = load_json(RESULTS_DUN)
    results.update(results_rows_from_snapshot(snapshot))
    write_json(RESULTS_DUN, results)
    write_json(LIVE, live_from_snapshot(snapshot))


def fetch_source():
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def main():
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--fetch", action="store_true", help="download the current Bernama official page")
    source.add_argument("--input", help="parse a downloaded Bernama official HTML page")
    parser.add_argument("--check", action="store_true", help="verify committed snapshot and generated outputs only")
    args = parser.parse_args()

    prn = load_json(PRN16)
    if args.fetch or args.input:
        raw = fetch_source() if args.fetch else open(args.input, encoding="utf-8").read()
        snapshot = parse_official_html(raw, prn)
        write_json(SNAPSHOT, snapshot, pretty=True)
    else:
        snapshot = load_json(SNAPSHOT)
        validate_snapshot(snapshot, prn)

    if not args.check:
        import_outputs(snapshot)
    validate_outputs(snapshot)
    print(
        f"Bernama/SPR Johor result verified: {len(snapshot['seats'])} seats, "
        f"{sum(len(s['candidates']) for s in snapshot['seats'].values())} candidates, "
        f"BN {snapshot['tally']['BN']} / PH {snapshot['tally']['PH']}"
    )


if __name__ == "__main__":
    main()
