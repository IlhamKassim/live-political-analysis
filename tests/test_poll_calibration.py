"""The rollup from published leader approval to a per-Coalition score.

This is the interpretation ADR 0004 records, and it is the only part of Poll
Calibration that is arithmetic rather than transcription — so the rules it
encodes are pinned here: net rather than raw approval, unweighted across a
Coalition's leaders, and a leader with no Coalition reported rather than
folded in or dropped.
"""

from datetime import date

from pytest import approx, raises

from lpa.config import load_coalition_config, load_poll_calibrations
from lpa.poll_calibration import LeaderRating, coalition_net_approval


def rating(leader: str, satisfied: float, dissatisfied: float, coalition=None):
    return LeaderRating(
        leader=leader,
        satisfied=satisfied,
        dissatisfied=dissatisfied,
        coalition=coalition,
    )


def test_net_approval_is_the_published_gap_on_the_sentiment_scale():
    # 52% satisfied against 44% dissatisfied is a net of +8 points, which is
    # +0.08 on the -1..+1 axis the Sentiment trend is drawn on.
    assert rating("Anwar Ibrahim", 52, 44).net_approval == approx(0.08)


def test_the_published_percentages_are_not_rescaled_to_sum_to_100():
    # The reports carry neutral and unsure/refused answers, so 28/29 leaves
    # 43% unaccounted for. Rescaling would turn a near-even split into a
    # confident one; the missing share belongs to neither side.
    assert rating("Ahmad Samsuri Mokhtar", 28, 29).net_approval == approx(-0.01)


def test_a_coalitions_leaders_are_averaged_unweighted():
    # PN as the March 2026 report rates it: Muhyiddin -19, Samsuri -1,
    # Hadi -30, giving -50/3 points.
    scores = coalition_net_approval(
        [
            rating("Muhyiddin Yassin", 36, 55, "PN"),
            rating("Ahmad Samsuri Mokhtar", 28, 29, "PN"),
            rating("Abdul Hadi Awang", 25, 55, "PN"),
        ]
    )

    assert scores.scores["PN"] == approx(-0.50 / 3)
    assert scores.leader_counts["PN"] == 3


def test_a_leader_with_no_coalition_is_named_rather_than_scored():
    # Khairy Jamaluddin belonged to no Coalition during the March 2026
    # fieldwork. His 50% must not reach BN, and must not vanish either.
    scores = coalition_net_approval(
        [
            rating("Ahmad Zahid Hamidi", 24, 61, "BN"),
            rating("Khairy Jamaluddin", 50, 31),
        ]
    )

    assert scores.scores == {"BN": approx(-0.37)}
    assert scores.leader_counts == {"BN": 1}
    assert scores.unattributed == ("Khairy Jamaluddin",)


def test_a_coalition_the_report_did_not_rate_is_absent_not_zero():
    # Merdeka Center rates no GPS or GRS leader. Scoring them 0.0 would put
    # them on the chart as measured neutrality nobody surveyed.
    scores = coalition_net_approval([rating("Anwar Ibrahim", 52, 44, "PH")])

    assert set(scores.scores) == {"PH"}


def test_a_report_that_rated_nobody_yields_no_scores():
    scores = coalition_net_approval([])

    assert scores.scores == {}
    assert scores.unattributed == ()


def test_the_shipped_transcription_is_the_real_march_2026_report():
    # Verified against the published PDF (merdeka.org/91060-2/): 1,209
    # respondents, fielded 12 March to 9 April 2026, margin of error 2.82%.
    reports = load_poll_calibrations()

    report = next(r for r in reports if r.fieldwork_end == date(2026, 4, 9))
    assert report.publisher == "Merdeka Center"
    assert report.sample_size == 1209
    assert report.fieldwork_start == date(2026, 3, 12)
    assert report.margin_of_error == 2.82

    anwar = next(r for r in report.leader_ratings if r.leader == "Anwar Ibrahim")
    assert (anwar.satisfied, anwar.dissatisfied) == (52, 44)
    assert anwar.coalition == "PH"


def test_every_transcribed_coalition_is_one_the_config_names(tmp_path):
    # A typo'd Coalition would otherwise be scored and charted beside the real
    # ones, looking exactly like a Coalition nobody had heard of doing badly.
    known = set(load_coalition_config()["coalition_aliases"])

    assert load_poll_calibrations(known_coalitions=known)

    typo = tmp_path / "poll_calibration.json"
    typo.write_text(
        _report_json(coalition="PHH", fieldwork_start="2026-03-12"),
    )
    with raises(ValueError, match="PHH"):
        load_poll_calibrations(typo, known_coalitions=known)


def test_a_report_cannot_close_its_fieldwork_before_it_opens(tmp_path):
    # Fieldwork end is what a poll is keyed and plotted on, so a swapped pair
    # of dates would file the report under the wrong day of the trend.
    backwards = tmp_path / "poll_calibration.json"
    backwards.write_text(_report_json(coalition="PH", fieldwork_start="2026-05-01"))

    with raises(ValueError, match="before it starts"):
        load_poll_calibrations(backwards)


def _report_json(*, coalition: str, fieldwork_start: str) -> str:
    return f"""
    {{"reports": [{{
        "publisher": "Merdeka Center",
        "title": "Test report",
        "report_url": "https://merdeka.org/",
        "published_on": "2026-06-25",
        "fieldwork_start": "{fieldwork_start}",
        "fieldwork_end": "2026-04-09",
        "sample_size": 1000,
        "leader_ratings": [
            {{"leader": "A", "coalition": "{coalition}",
              "satisfied": 50, "dissatisfied": 40}}
        ]
    }}]}}
    """


def test_a_report_without_a_margin_of_error_still_loads(tmp_path):
    # Not every report prints one, and a missing margin is no reason to
    # refuse a poll that was published.
    path = tmp_path / "poll_calibration.json"
    path.write_text(_report_json(coalition="PH", fieldwork_start="2026-03-12"))

    assert load_poll_calibrations(path)[0].margin_of_error is None
