"""The shipped Coalition configuration is data the Swing Model depends on, so
it is checked against the documented Government Coalition rather than left to
be discovered wrong at run time.
"""

from lpa.config import (
    coalition_aliases,
    load_coalition_config,
    load_outlets,
    party_to_coalition,
    swing_model_config,
)
from lpa.sentiment import attribute_sentences


def test_the_shipped_config_names_the_august_2026_government_coalition():
    # CONTEXT.md: "The current governing bloc — PH + BN + GPS + GRS plus minor
    # parties", and Majority is "more than half of the 222 seats (112+)".
    config = swing_model_config(load_coalition_config())

    assert config.government_coalitions == frozenset({"PH", "BN", "GPS", "GRS"})
    assert config.majority_threshold == 112


def test_component_parties_that_stood_alone_roll_up_to_their_coalition():
    # DAP and PAS appeared on GE15 ballots under their own banners where their
    # Coalition was not registered; their votes are PH's and PN's respectively.
    mapping = party_to_coalition(load_coalition_config())

    assert mapping["PARTI TINDAKAN DEMOKRATIK (DAP)"] == "PH"
    assert mapping["PARTI ISLAM SE MALAYSIA (PAS)"] == "PN"


def test_the_shipped_aliases_read_bahasa_malaysia_coverage():
    # Issue #13: the Malay outlets are only worth reading if the aliases find
    # the Coalitions in Malay prose, which is where these sentences come from.
    aliases = coalition_aliases(load_coalition_config())

    assert "BN" in attribute_sentences(
        "Kemenangan Barisan Nasional (BN) pada dua Pilihan Raya Negeri.", aliases
    )
    assert "PN" in attribute_sentences(
        "Persefahaman BN dan PN menyaksikan gabungan itu diperkukuh.", aliases
    )
    assert "PH" in attribute_sentences(
        "Pengarah Komunikasi Pakatan Harapan berkata persefahaman itu kekal.", aliases
    )


def test_the_united_nations_is_not_coverage_of_gps():
    # "PBB" was a GPS alias until issue #13. In Bahasa Malaysia it is almost
    # always Pertubuhan Bangsa-Bangsa Bersatu, and this sentence — from Berita
    # Harian's feed on the first run that read it — scored a Hiroshima
    # anniversary as GPS sentiment. GPS is named rarely enough that a few UN
    # stories would have been most of its score.
    aliases = coalition_aliases(load_coalition_config())

    attributed = attribute_sentences(
        "Dalam mesej bagi pihak Setiausaha Agung Pertubuhan Bangsa-Bangsa "
        "Bersatu (PBB) António Guterres, Wakil Tinggi PBB berkata Hiroshima "
        "terus menjadi lambang keamanan.",
        aliases,
    )

    assert attributed == {}


def test_umno_is_found_in_the_mixed_case_most_outlets_write_it_in():
    # NST, FMT and Bernama all write "Umno", not "UMNO". Matching is
    # case-sensitive, so listing only the shouted form missed BN's commonest
    # alias in exactly the outlets that use it most.
    aliases = coalition_aliases(load_coalition_config())

    assert "BN" in attribute_sentences("Umno and DAP maintain cordial ties.", aliases)
    assert "BN" in attribute_sentences("UMNO menang 16 kerusi DUN.", aliases)


def test_the_scraper_reads_at_least_one_bahasa_malaysia_outlet():
    # Issue #13's standing risk is regression by deletion: drop these two and
    # News Sentiment goes back to being blind to Malay coverage silently.
    names = {outlet.name for outlet in load_outlets()}

    assert {"Berita Harian", "Utusan Malaysia"} <= names


def test_every_shipped_data_file_is_findable():
    # The wheel carries these beside the package while a checkout keeps them at
    # the repo root; resolving only the checkout layout broke installs.
    from lpa.config import data_file

    for name in (
        "coalitions.json",
        "outlets.json",
        "state_elections.json",
        "poll_calibration.json",
    ):
        assert data_file(name).exists(), name
