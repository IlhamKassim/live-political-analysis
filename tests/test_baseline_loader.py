"""The Baseline Loader's seam: raw public-dataset rows -> SeatBaseline records.

Fixture rows are trimmed copies of the real column layout, so the tests pin the
transform without reaching the network.
"""

from pytest import approx, fixture

from lpa.baseline_loader import build_seat_baselines

PARTY_TO_COALITION = {
    "PAKATAN HARAPAN (PH)": "PH",
    "PARTI TINDAKAN DEMOKRATIK (DAP)": "PH",
    "PERIKATAN NASIONAL (PN)": "PN",
    "PARTI ISLAM SE MALAYSIA (PAS)": "PN",
}

CANDIDATES = [
    # P.001: PN 6000, PH 4000 of 10000 -> PN by 20pp.
    {
        "state": "Perlis",
        "parlimen": "P.001 Padang Besar",
        "party": "PERIKATAN NASIONAL (PN)",
        "votes": "6000",
        "result": "1",
    },
    {
        "state": "Perlis",
        "parlimen": "P.001 Padang Besar",
        "party": "PAKATAN HARAPAN (PH)",
        "votes": "4000",
        "result": "0",
    },
    # P.002: PH banner 3000 + DAP banner 2000 = PH 5000, PN 3000, BEBAS 2000.
    {
        "state": "Perlis",
        "parlimen": "P.002 Kangar",
        "party": "PAKATAN HARAPAN (PH)",
        "votes": "3000",
        "result": "1",
    },
    {
        "state": "Perlis",
        "parlimen": "P.002 Kangar",
        "party": "PARTI TINDAKAN DEMOKRATIK (DAP)",
        "votes": "2000",
        "result": "0",
    },
    {
        "state": "Perlis",
        "parlimen": "P.002 Kangar",
        "party": "PARTI ISLAM SE MALAYSIA (PAS)",
        "votes": "3000",
        "result": "0",
    },
    {
        "state": "Perlis",
        "parlimen": "P.002 Kangar",
        "party": "BEBAS (BEBAS)",
        "votes": "2000",
        "result": "0",
    },
]

CENSUS = [
    {
        "parlimen": "P.001 Padang Besar",
        "ethnicity_proportion_bumi": "89.8",
        "ethnicity_proportion_chinese": "5.6",
        "ethnicity_proportion_indian": "1.6",
        "ethnicity_proportion_other": "2.9",
        "age_proportion_18_above": "69.3",
        "income_median": "4075",
    },
    {
        "parlimen": "P.002 Kangar",
        "ethnicity_proportion_bumi": "87.3",
        "ethnicity_proportion_chinese": "9.6",
        "ethnicity_proportion_indian": "1.5",
        "ethnicity_proportion_other": "1.6",
        "age_proportion_18_above": "70.0",
        "income_median": "4889",
    },
]


@fixture
def baselines() -> dict[str, object]:
    return {b.code: b for b in build_seat_baselines(CANDIDATES, CENSUS, PARTY_TO_COALITION)}


def test_rolls_candidate_votes_up_to_coalition_vote_share_per_seat(baselines):
    padang_besar = baselines["P.001"]
    assert padang_besar.name == "Padang Besar"
    assert padang_besar.state == "Perlis"
    assert padang_besar.vote_share == {"PN": 0.6, "PH": 0.4}
    assert padang_besar.winner == "PN"


def test_a_party_contesting_under_its_own_banner_counts_towards_its_coalition(baselines):
    # DAP stood separately from the PH banner in some seats. Its 2000 votes
    # belong to PH's 3000, making PH the winner on 5000 of 10000.
    kangar = baselines["P.002"]
    assert kangar.vote_share == {"PH": 0.5, "PN": 0.3, "BEBAS": 0.2}
    assert kangar.winner == "PH"


def test_an_unmapped_party_keeps_its_own_short_code_rather_than_joining_a_bloc(baselines):
    # BEBAS (independents) is absent from the map. Folding it into a catch-all
    # bloc would invent a contender that never stood.
    assert "BEBAS" in baselines["P.002"].vote_share


def test_margin_is_the_winners_lead_over_the_runner_up_in_vote_share(baselines):
    assert baselines["P.001"].margin == approx(0.2)  # PN 0.60 - PH 0.40
    assert baselines["P.002"].margin == approx(0.2)  # PH 0.50 - PN 0.30


def test_demographics_are_carried_through_from_the_census(baselines):
    assert baselines["P.001"].demographics == {
        "ethnicity_proportion_bumi": 89.8,
        "ethnicity_proportion_chinese": 5.6,
        "ethnicity_proportion_indian": 1.6,
        "ethnicity_proportion_other": 2.9,
        "age_proportion_18_above": 69.3,
        "income_median": 4075.0,
    }
