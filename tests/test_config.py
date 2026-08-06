"""The shipped Coalition configuration is data the Swing Model depends on, so
it is checked against the documented Government Coalition rather than left to
be discovered wrong at run time.
"""

from lpa.config import load_coalition_config, party_to_coalition, swing_model_config


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
