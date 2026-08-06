"""Storage is verified manually at MVP (issue #1's Testing Decisions), but
issue #3 makes re-running the loader safely an explicit acceptance criterion,
so that one behaviour is pinned here against in-memory SQLite.
"""

from dataclasses import replace
from datetime import date

from pytest import raises

from fixtures import PH, PN, two_coalition_seats
from lpa.poll_calibration import LeaderRating, PollCalibration
from lpa.storage import (
    connect,
    load_poll_calibrations,
    load_seat_baselines,
    save_poll_calibrations,
    save_seat_baselines,
)


def test_running_the_loader_twice_leaves_one_copy_of_each_seat():
    engine = connect("sqlite+pysqlite:///:memory:")
    baselines = two_coalition_seats()

    save_seat_baselines(engine, baselines)
    save_seat_baselines(engine, baselines)

    stored = load_seat_baselines(engine)
    assert [b.code for b in stored] == ["P001", "P002", "P003", "P004", "P005", "P006"]


def test_a_stored_baseline_reads_back_as_it_was_written():
    engine = connect("sqlite+pysqlite:///:memory:")

    save_seat_baselines(engine, two_coalition_seats())
    stored = {b.code: b for b in load_seat_baselines(engine)}

    assert stored["P001"].vote_share == {PH: 0.60, PN: 0.40}
    assert stored["P001"].state == "Selangor"


def test_refuses_to_replace_the_stored_baseline_with_nothing():
    # An empty fetch must not be allowed to destroy the snapshot the dashboard
    # is serving — there would be nothing to restore it from.
    engine = connect("sqlite+pysqlite:///:memory:")
    save_seat_baselines(engine, two_coalition_seats())

    with raises(ValueError):
        save_seat_baselines(engine, [])

    assert len(load_seat_baselines(engine)) == 6


def test_margin_and_demographics_survive_the_round_trip():
    engine = connect("sqlite+pysqlite:///:memory:")
    baseline = replace(
        two_coalition_seats()[0],
        margin=0.2,
        demographics={"ethnicity_proportion_bumi": 89.8, "income_median": 4075.0},
    )

    save_seat_baselines(engine, [baseline])

    assert load_seat_baselines(engine)[0] == baseline


def poll(fieldwork_end: date, publisher: str = "Merdeka Center", **overrides):
    defaults = dict(
        publisher=publisher,
        title="Perceptions Towards Economy, Leadership & Current Issues",
        report_url="https://merdeka.org/91060-2/",
        published_on=date(2026, 6, 25),
        fieldwork_start=date(2026, 3, 12),
        fieldwork_end=fieldwork_end,
        sample_size=1209,
        margin_of_error=2.82,
        leader_ratings=(
            LeaderRating(
                leader="Anwar Ibrahim",
                satisfied=52,
                dissatisfied=44,
                party="PKR",
                coalition="PH",
            ),
            LeaderRating(
                leader="Khairy Jamaluddin",
                satisfied=50,
                dissatisfied=31,
                note="Outside UMNO during fieldwork.",
            ),
        ),
    )
    return PollCalibration(**{**defaults, **overrides})


def test_a_stored_poll_calibration_reads_back_verbatim():
    # The published percentages and the attribution are the whole record — a
    # Poll Calibration point is hand-copied from a PDF, and anything the round
    # trip loses cannot be recovered from Storage.
    engine = connect("sqlite+pysqlite:///:memory:")
    report = poll(date(2026, 4, 9))

    save_poll_calibrations(engine, [report])

    assert load_poll_calibrations(engine) == [report]


def test_re_ingesting_a_report_corrects_it_rather_than_duplicating_it():
    # Fixing a transcription error is editing the data file and running the
    # loader again, so the second run must replace the first answer.
    engine = connect("sqlite+pysqlite:///:memory:")
    save_poll_calibrations(engine, [poll(date(2026, 4, 9), sample_size=1209)])

    save_poll_calibrations(engine, [poll(date(2026, 4, 9), sample_size=1206)])

    stored = load_poll_calibrations(engine)
    assert [r.sample_size for r in stored] == [1206]


def test_ingesting_does_not_delete_reports_missing_from_this_run():
    # Unlike the Baseline this is not a wholesale replacement: reports pile up
    # over years, and trimming the data file must not erase the history.
    engine = connect("sqlite+pysqlite:///:memory:")
    save_poll_calibrations(engine, [poll(date(2025, 5, 20))])

    save_poll_calibrations(engine, [poll(date(2026, 4, 9))])

    assert [r.fieldwork_end for r in load_poll_calibrations(engine)] == [
        date(2025, 5, 20),
        date(2026, 4, 9),
    ]


def test_two_publishers_can_close_fieldwork_on_the_same_day():
    engine = connect("sqlite+pysqlite:///:memory:")

    save_poll_calibrations(
        engine,
        [poll(date(2026, 4, 9)), poll(date(2026, 4, 9), publisher="Ilham Centre")],
    )

    assert len(load_poll_calibrations(engine)) == 2
