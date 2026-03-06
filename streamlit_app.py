import os
import tempfile
from typing import Dict, List, Optional

import streamlit as st

from parser import parse_pdf
from storage import (
    WordEntry,
    active_study_words,
    list_words,
    load_bank,
    mark_seen,
    reset_to_unseen,
    save_bank,
    set_state,
    upsert_words_merge_by_en,
)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_BANK_PATH = os.path.join(os.path.dirname(__file__), "word_bank.json")

CATEGORY_ORDER = [
    "Business", "Consumer Affairs", "Employment", "Health",
    "Immigration/settlement", "Legal", "Community", "Education",
    "Financial", "Housing", "Insurance", "Social Services",
]
_CATEGORY_RANK = {c.lower(): i for i, c in enumerate(CATEGORY_ORDER)}


# ── Bank helpers ──────────────────────────────────────────────────────────────

def _bank_path() -> str:
    return st.session_state.get("bank_path") or DEFAULT_BANK_PATH


def _load_bank() -> Dict:
    bank = load_bank(_bank_path())
    st.session_state["bank"] = bank
    return bank


def _save_bank(bank: Dict) -> None:
    save_bank(_bank_path(), bank)
    st.session_state["bank"] = bank


def _bank() -> Dict:
    return st.session_state["bank"] if "bank" in st.session_state else _load_bank()


def _sort_categories(categories) -> List[str]:
    known   = [c for c in CATEGORY_ORDER if c in categories]
    unknown = sorted(c for c in categories if c not in known)
    return known + unknown


def _word(bank: Dict, en: str) -> Optional[WordEntry]:
    return next((w for w in list_words(bank) if w.en == en), None)


# ── Pages ─────────────────────────────────────────────────────────────────────

def page_import() -> None:
    st.subheader("Import")
    st.caption("Upload the CCL ˃⩊˂ vocab PDF. New entries will be merged into your local word bank (duplicates skipped by English).")

    with st.expander("Storage", expanded=False):
        st.text_input("Word bank JSON path", value=_bank_path(), key="bank_path")
        st.button("Reload word bank from disk", on_click=_load_bank, use_container_width=True)

    bank = _bank()
    st.info(f"Current word bank: **{len(list_words(bank))}** words.")

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if not uploaded:
        return

    col_parse, col_dry = st.columns(2)
    parse_now = col_parse.button("Parse + Merge into word bank", type="primary", use_container_width=True)
    dry_run   = col_dry.button("Parse only (no save)", use_container_width=True)

    if not (parse_now or dry_run):
        st.info("Click a button above to start parsing.")
        return

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.getbuffer())
        tmp_path = tmp.name

    try:
        with st.spinner("Parsing PDF..."):
            entries = parse_pdf(tmp_path)
        st.success(f"Parsed **{len(entries)}** entries from PDF.")

        if dry_run:
            st.write("Preview (first 20):")
            st.dataframe(entries[:20], use_container_width=True)
            return

        with st.spinner("Merging into local word bank..."):
            updated, added, skipped = upsert_words_merge_by_en(bank, entries)
            _save_bank(updated)

        st.success(f"Saved. Added **{added}**, skipped **{skipped}** duplicates. Total now **{len(list_words(updated))}**.")
        st.button("Go to Flashcards", on_click=lambda: st.session_state.update({"nav": "Flashcards"}))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Flashcard helpers ─────────────────────────────────────────────────────────

def _fc_init() -> None:
    st.session_state.setdefault("fc_flip", False)
    st.session_state.setdefault("fc_queue", [])
    st.session_state.setdefault("fc_current", None)


def _fc_build_queue(bank: Dict) -> List[str]:
    active = active_study_words(list_words(bank))
    active.sort(key=lambda w: (_CATEGORY_RANK.get(w.category.lower(), len(CATEGORY_ORDER)), w.en.lower()))
    return [w.en for w in active]


def _fc_advance(bank: Dict) -> Optional[str]:
    if not st.session_state.get("fc_queue"):
        st.session_state["fc_queue"] = _fc_build_queue(bank)
    queue = st.session_state.get("fc_queue") or []
    if not queue:
        st.session_state["fc_current"] = None
        return None
    nxt = queue.pop(0)
    st.session_state.update({"fc_queue": queue, "fc_current": nxt, "fc_flip": False})
    return nxt


def _fc_action(bank: Dict, en: str, new_state: str) -> None:
    word    = _word(bank, en)
    updated = mark_seen(bank, en) if (word and word.state == "unseen") else bank
    _save_bank(set_state(updated, en, new_state))
    _fc_advance(_bank())
    st.rerun()


def page_flashcards() -> None:
    st.subheader("Flashcards")
    st.caption("One card at a time. Reveal Chinese, then mark Mastered, Not Mastered, or Skip. Words follow category order.")

    bank = _bank()
    _fc_init()

    current_en = st.session_state.get("fc_current") or _fc_advance(bank)
    if current_en is None:
        st.success("No active study words left (all are mastered or not mastered).")
        if st.button("Go to Import", use_container_width=True):
            st.session_state["nav"] = "Import"
        return

    current = _word(bank, current_en)
    if current is None:
        _fc_advance(bank)
        st.rerun()

    st.write("")
    st.markdown(
        f"""
        <div style="padding:24px;border:1px solid rgba(255,255,255,0.15);border-radius:12px;">
          <div style="font-size:28px;font-weight:700;">{current.en}</div>
          <div style="opacity:0.75;margin-top:6px;">Category: {current.category} · State: {current.state}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    if not st.session_state.get("fc_flip"):
        if st.button("Reveal Chinese", use_container_width=True):
            st.session_state["fc_flip"] = True
            st.rerun()
        return

    st.markdown(
        f"""
        <div style="padding:20px;border:1px dashed rgba(255,255,255,0.25);border-radius:12px;">
          <div style="font-size:22px;">{current.zh}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    for col, label, state in [
        (col1, "Mastered",     "mastered"),
        (col2, "Not Mastered", "not_mastered"),
        (col3, "Skip",         "seen"),
    ]:
        if col.button(label, use_container_width=True):
            _fc_action(bank, current.en, state)

    st.caption(
        f"Queue remaining (this shuffle): {len(st.session_state.get('fc_queue') or [])}. "
        f"Active words remaining: {len(active_study_words(list_words(_bank())))}."
    )


def page_word_bank() -> None:
    st.subheader("Word Bank")
    st.caption("Browse all words grouped by state and category. You can reset individual words back to unseen.")

    bank  = _bank()
    words = list_words(bank)

    if not words:
        st.info("Your word bank is empty. Import a PDF first.")
        return

    states = ["unseen", "seen", "not_mastered", "mastered"]

    with st.expander("Quick stats", expanded=True):
        for col, state in zip(st.columns(4), states):
            col.metric(state, sum(1 for w in words if w.state == state))

    state_filter    = st.selectbox("State", options=states)
    category_filter = st.selectbox(
        "Category",
        options=["(All)"] + _sort_categories({w.category for w in words}),
    )

    filtered = [
        w for w in words
        if w.state == state_filter
        and (category_filter == "(All)" or w.category == category_filter)
    ]

    if not filtered:
        st.info("No words match the current filter.")
        return

    st.write(f"Showing **{len(filtered)}** words.")
    for w in filtered:
        with st.container(border=True):
            col_en, col_zh, col_btn = st.columns([3, 2, 1])
            col_en.markdown(f"**{w.en}**")
            col_zh.markdown(w.zh)
            if col_btn.button("Reset", key=f"reset:{w.en}", use_container_width=True):
                _save_bank(reset_to_unseen(bank, w.en))
                st.rerun()
            st.caption(f"Category: {w.category} · Source: {w.src or '—'} · Seen count: {w.seen_count}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(page_title="LEXIS — CCL Vocabulary Study", layout="wide")
    st.title("LEXIS")

    pages = {"Import": page_import, "Flashcards": page_flashcards, "Word Bank": page_word_bank}
    nav = st.sidebar.radio("Navigate", options=list(pages), key="nav")
    pages[nav]()


if __name__ == "__main__":
    main()