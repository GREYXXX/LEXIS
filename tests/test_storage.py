import json
import os
import tempfile

from storage import (
    WordEntry,
    active_study_words,
    list_words,
    load_bank,
    mark_seen,
    normalize_en,
    reset_to_unseen,
    save_bank,
    set_state,
    upsert_words_merge_by_en,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bank(*entries):
    """Build a minimal bank dict from a list of plain dicts."""
    return {"version": 1, "updated_at": 0.0, "words": list(entries)}


def word(en, zh="中文", src="1", category="Test", state="unseen", seen_count=0):
    return {"en": en, "zh": zh, "src": src, "category": category, "state": state, "seen_count": seen_count}


# ---------------------------------------------------------------------------
# normalize_en
# ---------------------------------------------------------------------------

def test_normalize_en_lowercases():
    assert normalize_en("Hello World") == "hello world"


def test_normalize_en_strips_and_collapses_whitespace():
    assert normalize_en("  multiple   spaces  ") == "multiple spaces"


def test_normalize_en_empty():
    assert normalize_en("") == ""


# ---------------------------------------------------------------------------
# WordEntry round-trip
# ---------------------------------------------------------------------------

def test_word_entry_from_any_defaults():
    w = WordEntry.from_any({})
    assert w.state == "unseen"
    assert w.seen_count == 0
    assert w.category == "Unknown"


def test_word_entry_round_trip():
    raw = word("breach", "违约", "CCL-12", "Legal", "seen", 2)
    w = WordEntry.from_any(raw)
    out = w.to_json()
    assert out["en"] == "breach"
    assert out["zh"] == "违约"
    assert out["state"] == "seen"
    assert out["seen_count"] == 2


# ---------------------------------------------------------------------------
# list_words
# ---------------------------------------------------------------------------

def test_list_words_empty_bank():
    assert list_words({"words": []}) == []


def test_list_words_returns_entries():
    bank = make_bank(word("annex"), word("clause"))
    words = list_words(bank)
    assert len(words) == 2
    assert {w.en for w in words} == {"annex", "clause"}


def test_list_words_skips_non_dicts():
    bank = {"words": [word("ok"), "not-a-dict", None, 42]}
    words = list_words(bank)
    assert len(words) == 1


# ---------------------------------------------------------------------------
# upsert_words_merge_by_en
# ---------------------------------------------------------------------------

def test_upsert_adds_new_words():
    bank = make_bank()
    new = [word("tender"), word("arbitration")]
    updated, added, skipped = upsert_words_merge_by_en(bank, new)
    assert added == 2
    assert skipped == 0
    assert len(list_words(updated)) == 2


def test_upsert_skips_exact_duplicate():
    bank = make_bank(word("tender"))
    updated, added, skipped = upsert_words_merge_by_en(bank, [word("tender")])
    assert added == 0
    assert skipped == 1
    assert len(list_words(updated)) == 1


def test_upsert_duplicate_is_case_insensitive():
    bank = make_bank(word("Tender"))
    updated, added, skipped = upsert_words_merge_by_en(bank, [word("TENDER")])
    assert skipped == 1
    assert len(list_words(updated)) == 1


def test_upsert_preserves_state_on_duplicate():
    bank = make_bank(word("tender", state="mastered", seen_count=3))
    updated, _, _ = upsert_words_merge_by_en(bank, [word("tender")])
    w = list_words(updated)[0]
    assert w.state == "mastered"
    assert w.seen_count == 3


def test_upsert_skips_entries_missing_en_or_zh():
    bank = make_bank()
    bad = [{"en": "", "zh": "中文"}, {"en": "word", "zh": ""}]
    updated, added, skipped = upsert_words_merge_by_en(bank, bad)
    assert added == 0
    assert len(list_words(updated)) == 0


# ---------------------------------------------------------------------------
# mark_seen
# ---------------------------------------------------------------------------

def test_mark_seen_transitions_unseen_to_seen():
    bank = make_bank(word("waiver", state="unseen", seen_count=0))
    updated = mark_seen(bank, "waiver")
    w = list_words(updated)[0]
    assert w.state == "seen"
    assert w.seen_count == 1


def test_mark_seen_does_not_change_already_seen():
    bank = make_bank(word("waiver", state="seen", seen_count=1))
    updated = mark_seen(bank, "waiver")
    w = list_words(updated)[0]
    assert w.state == "seen"
    assert w.seen_count == 1


def test_mark_seen_does_not_change_mastered():
    bank = make_bank(word("waiver", state="mastered", seen_count=5))
    updated = mark_seen(bank, "waiver")
    w = list_words(updated)[0]
    assert w.state == "mastered"


# ---------------------------------------------------------------------------
# set_state
# ---------------------------------------------------------------------------

def test_set_state_mastered():
    bank = make_bank(word("liability", state="seen"))
    updated = set_state(bank, "liability", "mastered")
    assert list_words(updated)[0].state == "mastered"


def test_set_state_not_mastered():
    bank = make_bank(word("liability", state="seen"))
    updated = set_state(bank, "liability", "not_mastered")
    assert list_words(updated)[0].state == "not_mastered"


def test_set_state_increments_seen_count_when_transitioning_from_unseen():
    bank = make_bank(word("escrow", state="unseen", seen_count=0))
    updated = set_state(bank, "escrow", "mastered")
    assert list_words(updated)[0].seen_count == 1


def test_set_state_does_not_touch_other_words():
    bank = make_bank(word("alpha"), word("beta"))
    updated = set_state(bank, "alpha", "mastered")
    words = {w.en: w for w in list_words(updated)}
    assert words["alpha"].state == "mastered"
    assert words["beta"].state == "unseen"


# ---------------------------------------------------------------------------
# reset_to_unseen
# ---------------------------------------------------------------------------

def test_reset_to_unseen_from_mastered():
    bank = make_bank(word("deed", state="mastered", seen_count=4))
    updated = reset_to_unseen(bank, "deed")
    w = list_words(updated)[0]
    assert w.state == "unseen"
    assert w.seen_count == 4  # seen_count is preserved


def test_reset_to_unseen_from_not_mastered():
    bank = make_bank(word("deed", state="not_mastered"))
    updated = reset_to_unseen(bank, "deed")
    assert list_words(updated)[0].state == "unseen"


# ---------------------------------------------------------------------------
# active_study_words
# ---------------------------------------------------------------------------

def test_active_study_words_includes_unseen_and_seen():
    words = [
        WordEntry.from_any(word("a", state="unseen")),
        WordEntry.from_any(word("b", state="seen")),
        WordEntry.from_any(word("c", state="mastered")),
        WordEntry.from_any(word("d", state="not_mastered")),
    ]
    active = active_study_words(words)
    assert {w.en for w in active} == {"a", "b"}


def test_active_study_words_empty_when_all_done():
    words = [
        WordEntry.from_any(word("x", state="mastered")),
        WordEntry.from_any(word("y", state="not_mastered")),
    ]
    assert active_study_words(words) == []


# ---------------------------------------------------------------------------
# save_bank / load_bank  (disk round-trip)
# ---------------------------------------------------------------------------

def test_save_and_load_round_trip():
    bank = make_bank(word("injunction", state="seen", seen_count=2))
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_bank(path, bank)
        loaded = load_bank(path)
        words = list_words(loaded)
        assert len(words) == 1
        assert words[0].en == "injunction"
        assert words[0].state == "seen"
        assert words[0].seen_count == 2
    finally:
        os.unlink(path)


def test_load_bank_missing_file_returns_default():
    bank = load_bank("/tmp/lexis_nonexistent_bank_xyz.json")
    assert bank["words"] == []
    assert bank["version"] == 1


def test_save_bank_is_valid_json():
    bank = make_bank(word("promissory", zh="期票"))
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        save_bank(path, bank)
        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)
        assert parsed["words"][0]["zh"] == "期票"
    finally:
        os.unlink(path)
