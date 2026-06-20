from gmail_cleaner.analyze import (
    extract_email,
    extract_domain,
    canonical_email,
    matches_pattern,
    matches_protected,
    matches_auto_delete,
    load_data
)


def test_extract_email():
    assert extract_email("John Doe <john@example.com>") == "john@example.com"
    assert extract_email("john@example.com") == "john@example.com"
    assert extract_email(None) == ""


def test_extract_domain():
    assert extract_domain("John Doe <john@example.com>") == "example.com"
    assert extract_domain("no-reply@sub.domain.com") == "sub.domain.com"
    assert extract_domain("invalid-email") == "(unknown)"


def test_canonical_email():
    assert canonical_email("John Doe <john@example.com>") == "john@example.com"
    assert canonical_email("John Doe <John@Example.COM>") == "john@example.com"


def test_matches_pattern():
    patterns = ["@spam.com", "exact@match.com"]
    assert matches_pattern("user@spam.com", patterns) is True
    assert matches_pattern("exact@match.com", patterns) is True
    assert matches_pattern("user@notspam.com", patterns) is False


def test_matches_protected(mock_config):
    # From conftest mock: ["vip@bank.com", "@mywork.com"]
    assert matches_protected("user@mywork.com") is True
    assert matches_protected("vip@bank.com") is True
    assert matches_protected("other@bank.com") is False


def test_matches_auto_delete(mock_config):
    # From conftest mock: ["spam@trash.com", "@junk.com"]
    assert matches_auto_delete("spam@trash.com") is True
    assert matches_auto_delete("user@junk.com") is True
    assert matches_auto_delete("user@good.com") is False


def test_load_data(mock_db, mock_config):
    df = load_data()

    # "alerts@mywork.com" should be filtered out because it matches PROTECTED_EMAIL_PATTERNS
    emails = df["email"].tolist()
    assert "alerts@mywork.com" not in emails

    # "spam@trash.com" should still be there (it gets matched later by auto delete strategies)
    assert "spam@trash.com" in emails

    # The dataframe should have 6 rows (7 synthetic - 1 protected)
    assert len(df) == 6
