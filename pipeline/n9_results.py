#!/usr/bin/env python3
"""Import the official 2026 Negeri Sembilan state-election result published by Bernama.

Bernama labels the result as official and attributes it to SPR. The server-rendered
page contains all 36 seats and 103 candidates. Unlike Johor there is no local
nomination roster (the app never ran an N9 campaign mode), so the winner's actual
party comes from a curated map cross-checked against the 2026 Negeri Sembilan
state election Wikipedia table (UMNO 16 / MCA 2 / DAP 9 / PKR 2 / PAS 4 /
WAWASAN 3); the importer hard-asserts each mapped name token-matches the Bernama
winner and that party -> ballot-badge coalition is consistent. Non-winners keep
their ballot badge as party. This importer keeps a normalized, reviewable source
snapshot, updates the permanent DUN results, and drops stale Negeri Sembilan
current-ADUN photo records whose seat changed hands.

Refresh from the official page:
  python3 pipeline/n9_results.py --fetch

Import a previously downloaded page:
  python3 pipeline/n9_results.py --input /path/to/index.html

Rebuild from the committed normalized snapshot, or only verify existing outputs:
  python3 pipeline/n9_results.py
  python3 pipeline/n9_results.py --check
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
SOURCE_URL = "https://prn.bernama.com/n9/keputusan/official/index.php"
SNAPSHOT = os.path.join(PIPELINE, "n9_prn16_bernama.json")
RESULTS_DUN = os.path.join(PUBLIC_DATA, "results-dun.json")
CANDIDATES_DUN = os.path.join(PUBLIC_DATA, "candidates-dun-prn15.json")
ADUNS = os.path.join(PUBLIC_DATA, "aduns.json")
UA = "MyPolitikBot/1.0 (https://mypolitik.krackeddevs.com; election data audit)"

ELECTION = "PRN Negeri Sembilan 2026"
ELECTION_ID = "prn16-n9"
STATE_NAME = "Negeri Sembilan"
SEAT_PREFIX = "5_N."
SEAT_COUNT = 36
CANDIDATE_COUNT = 103

# Ballot badges as printed on the Bernama page. BERSATU ran outside PN in this
# election (24 candidates, zero winners); WAWASAN/PAS candidates carried the PN
# badge and UMNO/MCA the BN badge, so badges are coalition-level for the pact
# parties and party-level for everyone else.
SOURCE_PARTY_COUNTS = {
    "ASLI": 1, "BEBAS": 4, "BERJASA": 1, "BERSATU": 24,
    "BN": 25, "PH": 36, "PN": 11, "PSM": 1,
}
EXPECTED_TALLY = {"BN": 18, "PH": 11, "PN": 7}
BADGE_COALITION = {
    "BN": "BN", "PH": "PH", "PN": "PN",
    "BERSATU": "BERSATU", "BERJASA": "BERJASA",
    "ASLI": "ASLI", "PSM": "PSM", "BEBAS": "BEBAS",
}
PARTY_BADGE = {  # winner party -> the ballot badge it must carry
    "UMNO": "BN", "MCA": "BN",
    "DAP": "PH", "PKR": "PH",
    "PAS": "PN", "WAWASAN": "PN",
}
COALITION_FULL = {
    "BN": "Barisan Nasional",
    "PH": "Pakatan Harapan",
    "PN": "Perikatan Nasional",
}
PARTY_FULL = {
    "UMNO": "United Malays National Organisation",
    "MCA": "Malaysian Chinese Association",
    "DAP": "Democratic Action Party",
    "PKR": "Parti Keadilan Rakyat",
    "PAS": "Parti Islam Se-Malaysia",
    "WAWASAN": "Parti Wawasan Negara",
    "BERSATU": "Parti Pribumi Bersatu Malaysia",
    "BERJASA": "Parti Barisan Jemaah Islamiah Se-Malaysia",
    "ASLI": "Parti Orang Asli Malaysia",
    "PSM": "Parti Sosialis Malaysia",
    "BEBAS": "Independent",
}

# Winner name + actual party per seat, from the 2026 Negeri Sembilan state
# election results table (en.wikipedia.org/wiki/2026_Negeri_Sembilan_state_election,
# read 2 Aug 2026). Names are display-cased; validate_snapshot token-matches each
# against the Bernama/SPR winner so a placement error cannot ship silently.
WINNERS = {
    "5_N.01": ("John Siow Kong Choon", "MCA"),
    "5_N.02": ("Jalaluddin Alias", "UMNO"),
    "5_N.03": ("Mohd Razi Mohd Ali", "UMNO"),
    "5_N.04": ("Danni Rais", "WAWASAN"),
    "5_N.05": ("Mohd Fairuz Mohd Isa", "PAS"),
    "5_N.06": ("Mustapha Nagoor", "UMNO"),
    "5_N.07": ("Mohd Zaidy Abdul Kadir", "UMNO"),
    "5_N.08": ("Teo Kok Seong", "DAP"),
    "5_N.09": ("Mohd Asna Amin", "UMNO"),
    "5_N.10": ("Arul Kumar Jambunathan", "DAP"),
    "5_N.11": ("Chew Seh Yong", "DAP"),
    "5_N.12": ("Ho Weng Wah", "DAP"),
    "5_N.13": ("Razali Abu Samah", "WAWASAN"),
    "5_N.14": ("Mohamad Rafie Abdul Malek", "PAS"),
    "5_N.15": ("Ismail Lasim", "UMNO"),
    "5_N.16": ("Muhammad Sufian Maradzi", "UMNO"),
    "5_N.17": ("Qayyum Abd Jalil", "UMNO"),
    "5_N.18": ("S Leza Md Yasin", "UMNO"),
    "5_N.19": ("Saiful Yazan Sulaiman", "UMNO"),
    "5_N.20": ("Siti Nur Umaira Hasim", "UMNO"),
    "5_N.21": ("Nicole Tan Lee Koon", "DAP"),
    "5_N.22": ("Desmond Siau Meow Kong", "DAP"),
    "5_N.23": ("Lee Kai Yet", "DAP"),
    "5_N.24": ("Mugunthan Subramaniam", "DAP"),
    "5_N.25": ("Kamarol Ridzuan Mohd Zain", "PAS"),
    "5_N.26": ("Zaifulbahri Idris", "UMNO"),
    "5_N.27": ("Mohamad Hasan", "UMNO"),
    "5_N.28": ("Suhaimi Aini", "UMNO"),
    "5_N.29": ("Yew Boon Lye", "PKR"),
    "5_N.30": ("Choo Ken Hwa", "DAP"),
    "5_N.31": ("Abdul Fatah Zakaria", "PAS"),
    "5_N.32": ("Mohd Faizal Ramli", "UMNO"),
    "5_N.33": ("Rajasekaran Gunnasekaran", "PKR"),
    "5_N.34": ("Ridzuan Ahmad", "WAWASAN"),
    "5_N.35": ("Suhaimizan Bizar", "UMNO"),
    "5_N.36": ("Koh Kim Swee", "MCA"),
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data, pretty=False):
    # No trailing newline: 03/04 write the same public/data files with plain
    # json.dump, and a byte flip-flop between rebuild paths defeats the
    # rebuild-must-be-byte-identical regression gate.
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(value).split())


def integer(value):
    return int(clean_text(value).replace(",", ""))


def title_case_name(value):
    particles = {"bin", "binti", "bt", "a/l", "a/p", "anak", "al", "@"}
    words = []
    for word in (value or "").split():
        low = word.lower()
        if low in particles:
            words.append(low)
        else:
            # capitalize each dotted segment too: "G.MANIVANNAN" -> "G.Manivannan"
            words.append(".".join(part.capitalize() for part in low.split(".")))
    return " ".join(words)


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
        "ballot_order": integer(match.group(2)),
        "votes": integer(match.group(7)),
        "winner": bool(match.group("winner")),
        "sex": "F" if clean_text(match.group(5)).upper() == "PEREMPUAN" else "M",
        "age": integer(match.group(6)),
    }


def enrich_candidate(code, source_candidate):
    badge = source_candidate["source_party"]
    if badge not in BADGE_COALITION:
        raise ValueError(f"{code}: unknown ballot badge {badge!r}")
    candidate = {
        "name": title_case_name(source_candidate["source_name"]),
        "source_name": source_candidate["source_name"],
        "party": badge,
        "coalition": BADGE_COALITION[badge],
        "source_party": badge,
        "ballot_order": source_candidate["ballot_order"],
        "votes": source_candidate["votes"],
        "winner": source_candidate["winner"],
        "sex": source_candidate["sex"],
        "age": source_candidate["age"],
    }
    if candidate["winner"]:
        name, party = WINNERS[code]
        if PARTY_BADGE[party] != badge:
            raise ValueError(f"{code}: winner party {party} cannot carry badge {badge}")
        if not same_person(name, source_candidate["source_name"]):
            raise ValueError(
                f"{code}: mapped winner {name!r} does not match "
                f"Bernama winner {source_candidate['source_name']!r}"
            )
        candidate["name"] = name
        candidate["party"] = party
    return candidate


def parse_official_html(raw, retrieved_at=None):
    if "Keputusan RASMI" not in raw or "Sumber : SPR" not in raw:
        raise ValueError("page is not marked as Bernama official results sourced from SPR")
    anchor = raw.find("Maklumat Calon & Keputusan Penuh PRN Negeri Sembilan 2026")
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
        code = f"{SEAT_PREFIX}{header.group(1)}"
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
        candidates = [enrich_candidate(code, c) for c in source_candidates]
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
        "election": ELECTION,
        "election_id": ELECTION_ID,
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
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot):
    seats = snapshot.get("seats") or {}
    expected_codes = {f"{SEAT_PREFIX}{number:02d}" for number in range(1, SEAT_COUNT + 1)}
    if set(seats) != expected_codes:
        raise ValueError(f"official seat coverage mismatch: {len(seats)}/{SEAT_COUNT}")
    badge_counts = collections.Counter()
    winner_counts = collections.Counter()
    winner_parties = collections.Counter()
    candidate_count = 0
    for code, seat in seats.items():
        candidates = seat.get("candidates") or []
        candidate_count += len(candidates)
        badge_counts.update(c["source_party"] for c in candidates)
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
        mapped_name, mapped_party = WINNERS[code]
        if winner["name"] != mapped_name or winner["party"] != mapped_party:
            raise ValueError(f"{code}: winner {winner['name']}/{winner['party']} differs from map")
        if PARTY_BADGE[mapped_party] != winner["source_party"]:
            raise ValueError(f"{code}: winner badge {winner['source_party']} inconsistent with {mapped_party}")
        winner_counts[winner["coalition"]] += 1
        winner_parties[winner["party"]] += 1
    if candidate_count != CANDIDATE_COUNT:
        raise ValueError(f"official candidate coverage mismatch: {candidate_count}/{CANDIDATE_COUNT}")
    if dict(sorted(badge_counts.items())) != SOURCE_PARTY_COUNTS:
        raise ValueError(f"candidate badge counts differ: {dict(badge_counts)}")
    if dict(sorted(winner_counts.items())) != EXPECTED_TALLY:
        raise ValueError(f"winner tally differs: {dict(winner_counts)}")
    if dict(winner_parties) != {"UMNO": 16, "MCA": 2, "DAP": 9, "PKR": 2, "PAS": 4, "WAWASAN": 3}:
        raise ValueError(f"winner party split differs: {dict(winner_parties)}")
    if snapshot.get("tally") != EXPECTED_TALLY:
        raise ValueError(f"snapshot tally differs: {snapshot.get('tally')}")


def results_rows_from_snapshot(snapshot):
    rows = {}
    for code, seat in snapshot["seats"].items():
        ranked = sorted(seat["candidates"], key=lambda candidate: candidate["votes"], reverse=True)
        winner, runner = ranked[:2]
        valid_votes = sum(candidate["votes"] for candidate in ranked)
        rows[code] = {
            "state": STATE_NAME,
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


def candidates_entries_from_snapshot(snapshot):
    """Per-seat full candidate field for candidates-dun-prn15.json (the seat card's
    Candidates tab). The 2023 six-state entries in that file stay untouched; the
    36 Negeri Sembilan entries are replaced with the official 2026 field so the
    tab shows the poll the displayed result came from."""
    entries = {}
    for code, seat in snapshot["seats"].items():
        ranked = sorted(seat["candidates"], key=lambda candidate: candidate["votes"], reverse=True)
        valid_votes = sum(candidate["votes"] for candidate in ranked)
        entries[code] = {
            "election": "PRN 2026",
            "source": snapshot["source"],
            "source_url": snapshot["source_url"],
            "candidates": [
                {
                    "rank": rank,
                    "ballot_order": candidate["ballot_order"],
                    "name": candidate["name"],
                    "party": candidate["party"],
                    "party_full": PARTY_FULL.get(
                        candidate["party"],
                        COALITION_FULL.get(candidate["party"], candidate["party"]),
                    ),
                    "coalition": candidate["coalition"],
                    "coalition_full": COALITION_FULL.get(candidate["coalition"], candidate["coalition"]),
                    "votes": candidate["votes"],
                    "vote_pct": round(100 * candidate["votes"] / valid_votes, 1),
                    "result": "won" if candidate["winner"] else "lost",
                    "age": candidate["age"],
                }
                for rank, candidate in enumerate(ranked, 1)
            ],
        }
    return entries


NAME_NOISE = re.compile(
    r"\b(datuk|dato'?|seri|dr|haji|hajah|hajjah|hj|yb|yab|ustaz|ustazah|cikgu|bin|binti|bt|a/l|a/p|anak)\b"
)


def name_tokens(value):
    value = NAME_NOISE.sub(" ", (value or "").lower())
    return {token for token in re.findall(r"[a-z0-9]+", value) if len(token) >= 4}


def clean_name_key(value):
    return re.sub(r"[^a-z0-9]", "", NAME_NOISE.sub(" ", (value or "").lower()))


def same_person(left, right):
    """Same-identity guard. Deliberately strict: ONE shared token must not match —
    generic Malay name elements (Mohd/Mohamad/Abdul/Ahmad/…) survive the noise
    strip, so a single-token rule conflates different people whenever a seat
    changes hands between two 'Mohd X' holders. Match only on honorific-stripped
    key equality, key containment (short form of the same name), or >=2 shared
    long tokens."""
    left_key, right_key = clean_name_key(left), clean_name_key(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key or left_key in right_key or right_key in left_key:
        return True
    return len(name_tokens(left) & name_tokens(right)) >= 2


def reconcile_aduns(rows):
    """Drop Negeri Sembilan current-ADUN photo records whose seat changed hands.

    aduns.json is the sparse confident-photo layer built by 11_aduns.py from the
    then-current holders; a stale record would show the previous assemblyman's
    photo and Wikidata identity on the new winner's card."""
    aduns = load_json(ADUNS)
    dropped = []
    for code in [c for c in aduns if c.startswith(SEAT_PREFIX)]:
        if not same_person(aduns[code].get("name"), rows[code]["name"]):
            dropped.append(f"{code} ({aduns[code].get('name')})")
            del aduns[code]
            # Also remove the seat-keyed photo + Commons-meta cache: 11_aduns.py
            # keys both by SEAT code, so leaving them behind would attach the
            # previous holder's portrait to whoever is resolved for this seat next.
            slug = code.replace(".", "-")
            for stale in (
                os.path.join(ROOT, "public", "assets", "politicians", "dun", f"{slug}.webp"),
                os.path.join(PIPELINE, "raw", "aduns", f"{slug}.imginfo.json"),
            ):
                if os.path.exists(stale):
                    os.remove(stale)
    if dropped:
        write_json(ADUNS, aduns)
    return dropped


def validate_outputs(snapshot):
    expected_rows = results_rows_from_snapshot(snapshot)
    expected_candidates = candidates_entries_from_snapshot(snapshot)
    results = load_json(RESULTS_DUN)
    candidates = load_json(CANDIDATES_DUN)
    aduns = load_json(ADUNS)
    for code, expected in expected_rows.items():
        if results.get(code) != expected:
            raise ValueError(f"{code}: results-dun is not synchronized with Bernama snapshot")
        if candidates.get(code) != expected_candidates[code]:
            raise ValueError(f"{code}: candidates-dun is not synchronized with Bernama snapshot")
        adun = aduns.get(code)
        if adun and not same_person(adun.get("name"), expected["name"]):
            raise ValueError(f"{code}: stale current-ADUN record {adun.get('name')!r}")


def import_outputs(snapshot):
    results = load_json(RESULTS_DUN)
    rows = results_rows_from_snapshot(snapshot)
    results.update(rows)
    write_json(RESULTS_DUN, results)
    candidates = load_json(CANDIDATES_DUN)
    candidates.update(candidates_entries_from_snapshot(snapshot))
    write_json(CANDIDATES_DUN, candidates)
    return reconcile_aduns(rows)


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

    if args.fetch or args.input:
        raw = fetch_source() if args.fetch else open(args.input, encoding="utf-8").read()
        snapshot = parse_official_html(raw)
        if args.check:
            # --check must never overwrite the committed, reviewed snapshot; with a
            # source it verifies the live page still matches it (dry-run) instead.
            committed = load_json(SNAPSHOT)
            volatile = ("retrieved_at", "source_sha256", "source_updated")
            if ({k: v for k, v in snapshot.items() if k not in volatile}
                    != {k: v for k, v in committed.items() if k not in volatile}):
                raise ValueError("live page content differs from the committed snapshot — review before importing")
            snapshot = committed
        else:
            write_json(SNAPSHOT, snapshot, pretty=True)
    else:
        snapshot = load_json(SNAPSHOT)
        validate_snapshot(snapshot)

    dropped = []
    if not args.check:
        dropped = import_outputs(snapshot)
    validate_outputs(snapshot)
    print(
        f"Bernama/SPR Negeri Sembilan result verified: {len(snapshot['seats'])} seats, "
        f"{sum(len(s['candidates']) for s in snapshot['seats'].values())} candidates, "
        f"BN {snapshot['tally']['BN']} / PH {snapshot['tally']['PH']} / PN {snapshot['tally']['PN']}"
    )
    for note in dropped:
        print(f"  dropped stale current-ADUN record: {note}")


if __name__ == "__main__":
    main()
