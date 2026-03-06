# LEXIS

Local vocabulary study app for CCL / PTE exam preparation. Built with Python + Streamlit.

## Setup

```bash
uv pip install -r requirements.txt
```

## Run

```bash
streamlit run streamlit_app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## Usage

| Page | What it does |
|---|---|
| **Import** | Upload the CCL ˃⩊˂ vocab PDF. Parses it and merges new words into `word_bank.json`. Duplicates (matched by English) are skipped. |
| **Flashcards** | Study one card at a time. Click to reveal Chinese, then mark **Mastered** or **Not Mastered**. Marked words leave the active queue. |
| **Word Bank** | Browse all words filtered by state and category. Reset any word back to unseen. |

Word states: `unseen` → `seen` (on first view) → `mastered` or `not_mastered` (on marking).

## Tests

```bash
uv pip install pytest
pytest tests/ -v
```
