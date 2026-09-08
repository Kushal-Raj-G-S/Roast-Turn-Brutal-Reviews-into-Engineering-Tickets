"""
Tests for compute_issue_fingerprint — the stable cross-run issue identity
that regression_detection.sql partitions by.

This is the fix for a real logic bug: cluster_id is a fresh UUID per
upload, so LAG() over cluster_id can never match the same issue across
pipeline versions and the regression model silently reports nothing
forever. The fingerprint must be stable across runs for the same issue,
and distinct for different issues — that's exactly what these pin.
"""

from src.infrastructure.warehouse.bigquery_sink import compute_issue_fingerprint


def test_same_issue_produces_same_fingerprint_across_runs():
    a = compute_issue_fingerprint("App crashes on startup", ["crash", "startup"])
    b = compute_issue_fingerprint("App crashes on startup", ["crash", "startup"])
    assert a == b


def test_fingerprint_is_keyword_order_independent():
    """Clustering may emit keywords in a different order between runs."""
    a = compute_issue_fingerprint("Login fails", ["login", "auth", "token"])
    b = compute_issue_fingerprint("Login fails", ["token", "login", "auth"])
    assert a == b


def test_fingerprint_is_title_word_order_independent():
    a = compute_issue_fingerprint("crashes on startup", [])
    b = compute_issue_fingerprint("startup crashes on", [])
    assert a == b


def test_fingerprint_ignores_filler_words_and_case():
    """A re-worded title for the same issue should still match."""
    a = compute_issue_fingerprint("The app crashes on startup", [])
    b = compute_issue_fingerprint("App Crashes On Startup", [])
    assert a == b


def test_different_issues_produce_different_fingerprints():
    crash = compute_issue_fingerprint("App crashes on startup", ["crash"])
    billing = compute_issue_fingerprint("Subscription charged twice", ["billing"])
    assert crash != billing


def test_fingerprint_is_stable_length_and_hex():
    fp = compute_issue_fingerprint("Payment declined", ["payment"])
    assert len(fp) == 32
    assert all(c in "0123456789abcdef" for c in fp)


def test_handles_empty_and_none_inputs():
    """Clustering can produce an untitled cluster; must not raise."""
    assert compute_issue_fingerprint("", None)
    assert compute_issue_fingerprint("", [])
    assert compute_issue_fingerprint("title", None)


def test_keywords_contribute_to_identity():
    """Same title, materially different keywords -> different issue."""
    a = compute_issue_fingerprint("Error occurred", ["network", "timeout"])
    b = compute_issue_fingerprint("Error occurred", ["billing", "refund"])
    assert a != b
