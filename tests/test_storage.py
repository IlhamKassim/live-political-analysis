"""Storage is verified manually at MVP (issue #1's Testing Decisions), but
issue #3 makes re-running the loader safely an explicit acceptance criterion,
so that one behaviour is pinned here against in-memory SQLite.
"""

from fixtures import PH, PN, two_coalition_seats
from lpa.storage import connect, load_seat_baselines, save_seat_baselines


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
