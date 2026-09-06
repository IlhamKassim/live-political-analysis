from __future__ import annotations

import json

import merge_mp_profiles


def test_merge_mp_profiles_main_prints_accurate_exclusive_counts(monkeypatch, tmp_path, capsys):
    fake_mp_profiles = {
        "profiles": {
            "P.001": {"coalition": "PH"},
            "P.002": {"coalition": "BN"},
        }
    }
    fake_politicians = {
        "mps": {
            "P.001": {"coalition": "PH"},
            "P.003": {"coalition": "PN"},
        }
    }

    mp_profiles_file = tmp_path / "mp_profiles.json"
    politicians_file = tmp_path / "politicians.json"
    output_file = tmp_path / "mp-profiles-merged.json"

    mp_profiles_file.write_text(json.dumps(fake_mp_profiles), encoding="utf-8")
    politicians_file.write_text(json.dumps(fake_politicians), encoding="utf-8")

    monkeypatch.setattr(merge_mp_profiles, "MP_PROFILES_PATH", mp_profiles_file)
    monkeypatch.setattr(merge_mp_profiles, "POLITICIANS_PATH", politicians_file)
    monkeypatch.setattr(merge_mp_profiles, "OUTPUT_PATH", output_file)

    merge_mp_profiles.main()

    out = capsys.readouterr().out
    assert "3 Seats" in out
    assert "1 with both bio and legislative data" in out
    assert "1 with legislative only" in out
    assert "1 with bio only" in out
