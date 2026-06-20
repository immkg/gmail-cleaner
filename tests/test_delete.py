from gmail_cleaner.delete import (
    parse_selection,
    get_newsletter_candidates,
    get_promotion_candidates,
    get_top_sender_candidates,
    get_auto_delete_candidates,
    build_pattern_deletes
)


def test_parse_selection_single_values():
    assert parse_selection("1", 10) == {0}
    assert parse_selection("1, 3, 5", 10) == {0, 2, 4}


def test_parse_selection_ranges():
    assert parse_selection("1-5", 10) == {0, 1, 2, 3, 4}
    assert parse_selection("1-3, 5-6", 10) == {0, 1, 2, 4, 5}


def test_parse_selection_out_of_bounds():
    # 15 should be ignored as max_index is 10
    assert parse_selection("1, 15", 10) == {0}
    # Invalid parsing falls through gracefully or ignores
    assert parse_selection("-5", 10) == set()


def test_parse_selection_mixed():
    assert parse_selection("1, 3-5, 9", 10) == {0, 2, 3, 4, 8}


def test_get_newsletter_candidates(synthetic_df):
    candidates = list(get_newsletter_candidates(synthetic_df))
    # daily@news.com has 2 newsletter emails
    assert len(candidates) == 1
    assert candidates[0][0] == "daily@news.com"
    assert candidates[0][1] == 2


def test_get_promotion_candidates(synthetic_df):
    candidates = list(get_promotion_candidates(synthetic_df))
    # marketing@store.com has 2 promotions
    assert len(candidates) == 1
    assert candidates[0][0] == "marketing@store.com"
    assert candidates[0][1] == 2


def test_get_top_sender_candidates(synthetic_df):
    candidates = list(get_top_sender_candidates(synthetic_df))
    # marketing and daily both have 2
    senders = [c[0] for c in candidates]
    assert "marketing@store.com" in senders
    assert "daily@news.com" in senders
    assert "friend@gmail.com" in senders


def test_get_auto_delete_candidates(synthetic_df, mock_config):
    candidates = list(get_auto_delete_candidates(synthetic_df))
    assert len(candidates) == 1
    assert candidates[0][0] == "spam@trash.com"


def test_build_pattern_deletes(synthetic_df):
    sender_df = synthetic_df[synthetic_df["email"] == "marketing@store.com"]
    # 2 emails: "50% Discount on Shoes!" (msg3) and "Another coupon" (msg6)

    # Fake candidate list like what handle_sender creates
    # [(normalized_subject, count)]
    candidates = [
        ("another coupon", 1),
        ("<num>% discount on shoes!", 1)
    ]

    # Test selecting the first pattern ("another coupon")
    ids = build_pattern_deletes(sender_df, candidates, "1")
    assert len(ids) == 1
    assert ids[0] == "msg6"

    # Test selecting both patterns ("1, 2")
    ids = build_pattern_deletes(sender_df, candidates, "1, 2")
    assert len(ids) == 2
    assert "msg3" in ids
    assert "msg6" in ids

    # Test "keep 1" (k1) -> keeps the newest (msg6 which has internal_date 1005), deletes msg3 (1002)
    ids = build_pattern_deletes(sender_df, candidates, "k1")
    assert len(ids) == 1
    assert ids[0] == "msg3"

    # Test "delete all" (d) -> wait, "d" means don't delete any in the current logic. Let's check `if selection == "d": return []`
    ids = build_pattern_deletes(sender_df, candidates, "d")
    assert len(ids) == 0
