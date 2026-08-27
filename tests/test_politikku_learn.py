from datetime import date

from lpa.config import load_election_status
from lpa.politikku_learn import build_coalitions_page, build_glossary_page, build_process_page
from lpa.politikku_shell import Language


def test_learn_pages_render_with_politikku_shell():
    status = load_election_status()
    glossary = build_glossary_page(Language.EN, date(2026, 1, 1), status)
    coalitions = build_coalitions_page(Language.EN, date(2026, 1, 1), status)
    process = build_process_page(Language.EN, date(2026, 1, 1), status)

    for page in [glossary, coalitions, process]:
        assert "<!doctype html>" in page
        assert 'class="pk-header"' in page
        assert 'class="pk-footer"' in page

        # No legacy artifacts
        assert "register-a.css" not in page
        assert 'class="masthead"' not in page
        assert 'class="colophon"' not in page


def test_citation_claims_are_preserved():
    status = load_election_status()
    glossary = build_glossary_page(Language.EN, date(2026, 1, 1), status)
    coalitions = build_coalitions_page(Language.EN, date(2026, 1, 1), status)
    process = build_process_page(Language.EN, date(2026, 1, 1), status)

    assert glossary.count("data-claim") == 50
    assert coalitions.count("data-claim") == 47
    assert process.count("data-claim") == 16
