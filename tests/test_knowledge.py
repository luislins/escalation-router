import datetime as dt


def test_catalog_search_matches_keywords_and_phrases(toolbox):
    hits = toolbox.catalog.search("Donor wants a refund, Apple Pay charge was duplicated")
    assert hits[0]["team_id"] == "payments"
    assert "apple pay" in [kw for h in hits for kw in h["matched_keywords"]]


def test_history_search_finds_similar_escalation(toolbox):
    results = toolbox.history.search("salesforce is creating duplicate contacts")
    assert results[0]["id"] == "ESC-103"
    assert results[0]["team"] == "integrations"


def test_oncall_rotates_weekly(toolbox):
    week1 = toolbox.oncall.current("payments", dt.date(2026, 1, 5))
    week2 = toolbox.oncall.current("payments", dt.date(2026, 1, 12))
    assert week1 != week2
    assert toolbox.oncall.current("unknown-team") is None
