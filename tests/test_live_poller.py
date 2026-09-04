import json
import os
import sys
import tempfile
from pathlib import Path

# Add frontend/pipeline/live to sys.path
LIVE_DIR = Path(__file__).resolve().parent.parent / "frontend" / "pipeline" / "live"
if str(LIVE_DIR) not in sys.path:
    sys.path.insert(0, str(LIVE_DIR))

import johor_poller
import poller


def test_norm_code():
    by_code = {"1_N.01": {}, "1_N.02": {}, "4_N.01": {}, "13_N.82": {}, "P.001": {}}

    # Explicit canonical codes
    assert poller.norm_code("1_N.01", prefix="1_", by_code=by_code) == "1_N.01"
    assert poller.norm_code("4_N.01", prefix="4_", by_code=by_code) == "4_N.01"

    # Johor DUN numbers
    assert poller.norm_code("N.01", prefix="1_", by_code=by_code) == "1_N.01"
    assert poller.norm_code("N01", prefix="1_", by_code=by_code) == "1_N.01"
    assert poller.norm_code("N1", prefix="1_", by_code=by_code) == "1_N.01"
    assert poller.norm_code(1, prefix="1_", by_code=by_code) == "1_N.01"

    # Other states DUN numbers
    assert poller.norm_code("N.01", prefix="4_", by_code=by_code) == "4_N.01"
    assert poller.norm_code("N.82", prefix="13_", by_code=by_code) == "13_N.82"

    # Parliamentary codes
    assert poller.norm_code("P.001", prefix="", by_code=by_code) == "P.001"
    assert poller.norm_code("P001", prefix="", by_code=by_code) == "P.001"
    assert poller.norm_code("P.1", prefix="", by_code=by_code) == "P.001"


def test_load_election_config_prn16_johor():
    cfg = poller.load_election_config("prn16-johor")
    assert cfg["id"] == "prn16-johor"
    assert cfg["state"] == "Johor"
    assert cfg["tier"] == "dun"
    assert cfg["seat_prefix"] == "1_"
    assert cfg["total_seats"] == 56
    assert cfg["majority"] == 29
    assert os.path.basename(cfg["out_path"]) == "live-johor.json"
    assert os.path.basename(cfg["master_path"]) == "prn16-johor.json"


def test_load_election_config_custom_fallback():
    cfg = poller.load_election_config("prn17-melaka")
    assert cfg["id"] == "prn17-melaka"
    assert cfg["state"] == "Melaka"
    assert cfg["tier"] == "dun"
    assert os.path.basename(cfg["out_path"]) == "live-melaka.json"


def test_merge_state_machine():
    readings = [
        (
            "manual",
            {
                "1_N.01": {
                    "status": "official",
                    "coalition": "BN",
                    "party": "UMNO",
                    "name": "Winner A",
                    "majority": "1000",
                }
            },
        ),
        (
            "sinar",
            {
                "1_N.02": {
                    "status": "won",
                    "coalition": "PH",
                    "party": "DAP",
                    "name": "Leader B",
                    "majority": "500",
                    "votes": 5000,
                }
            },
        ),
        (
            "thestar",
            {
                "1_N.02": {
                    "status": "leading",
                    "coalition": "PH",
                    "party": "DAP",
                    "name": "Leader B",
                    "majority": "500",
                }
            },
        ),
        (
            "thestar",
            {
                "1_N.03": {
                    "status": "won",
                    "coalition": "PN",
                    "party": "PAS",
                    "name": "Leader C",
                    "majority": "200",
                }
            },
        ),
    ]
    merged = poller.merge(readings)

    # 1_N.01 has manual -> authoritative official
    assert merged["1_N.01"]["status"] == "official"
    assert merged["1_N.01"]["coalition"] == "BN"

    # 1_N.02 has two agreeing untrusted sources (sinar + thestar) -> promotes to won
    assert merged["1_N.02"]["status"] == "won"
    assert merged["1_N.02"]["coalition"] == "PH"
    assert merged["1_N.02"]["votes"] == 5000

    # 1_N.03 has only one untrusted source (thestar) -> capped to leading
    assert merged["1_N.03"]["status"] == "leading"
    assert merged["1_N.03"]["coalition"] == "PN"


def test_publish_and_fixture_run():
    fixture_path = LIVE_DIR / "fixtures" / "midcount.json"
    assert fixture_path.is_file()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "live-test.json"

        # Test running poller with --fixture
        rc = poller.main(
            "prn16-johor", argv=["--fixture", str(fixture_path), "--out", str(out_file)]
        )
        assert rc == 0
        assert out_file.is_file()

        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)

        assert data["phase"] == "live"
        assert data["election"] == "prn16-johor"
        assert data["source"] == "dress rehearsal fixture"
        assert "tally" in data
        assert data["tally"]["BN"] == 6
        assert data["tally"]["PH"] == 4
        assert data["tally"]["PN"] == 3
        assert len(data["seats"]) == 26
        assert data["seats"]["1_N.01"]["status"] == "won"


def test_johor_poller_wrapper():
    fixture_path = LIVE_DIR / "fixtures" / "midcount.json"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_file = Path(tmpdir) / "live-wrapper-test.json"

        rc = johor_poller.main(argv=["--fixture", str(fixture_path), "--out", str(out_file)])
        assert rc == 0
        assert out_file.is_file()

        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)

        assert data["phase"] == "live"
        assert data["election"] == "prn16-johor"
        assert data["tally"] == {"BN": 6, "PH": 4, "PN": 3}
