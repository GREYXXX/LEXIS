from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

WordState = Literal["unseen", "seen", "mastered", "not_mastered"]


def normalize_en(en: str) -> str:
    return " ".join(en.strip().lower().split())


@dataclass(frozen=True)
class WordEntry:
    en: str
    zh: str
    src: str
    category: str
    state: WordState = "unseen"
    seen_count: int = 0
    updated_at: float = 0.0

    @staticmethod
    def from_any(d: Dict[str, Any]) -> "WordEntry":
        return WordEntry(
            en=str(d.get("en", "")).strip(),
            zh=str(d.get("zh", "")).strip(),
            src=str(d.get("src", "")).strip(),
            category=str(d.get("category", "Unknown")).strip() or "Unknown",
            state=(d.get("state") or "unseen"),
            seen_count=int(d.get("seen_count") or 0),
            updated_at=float(d.get("updated_at") or 0.0),
        )

    def to_json(self) -> Dict[str, Any]:
        return {
            "en": self.en,
            "zh": self.zh,
            "src": self.src,
            "category": self.category,
            "state": self.state,
            "seen_count": self.seen_count,
            "updated_at": self.updated_at,
        }


def _default_bank() -> Dict[str, Any]:
    return {"version": 1, "updated_at": time.time(), "words": []}


def load_bank(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return _default_bank()
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or "words" not in raw:
        return _default_bank()
    if not isinstance(raw.get("words"), list):
        raw["words"] = []
    raw.setdefault("version", 1)
    raw.setdefault("updated_at", time.time())
    return raw


def save_bank(path: str, bank: Dict[str, Any]) -> None:
    bank = dict(bank)
    bank["updated_at"] = time.time()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def list_words(bank: Dict[str, Any]) -> List[WordEntry]:
    words = bank.get("words") or []
    if not isinstance(words, list):
        return []
    out: List[WordEntry] = []
    for item in words:
        if isinstance(item, dict):
            out.append(WordEntry.from_any(item))
    return out


def upsert_words_merge_by_en(
    bank: Dict[str, Any], new_entries: Iterable[Dict[str, Any]]
) -> Tuple[Dict[str, Any], int, int]:
    """
    Merge new entries into bank, skipping duplicates by normalized `en`.
    If an existing word is found, we keep its state/seen_count and update other fields if non-empty.
    Returns: (updated_bank, added_count, skipped_count)
    """
    existing = list_words(bank)
    by_key: Dict[str, WordEntry] = {normalize_en(w.en): w for w in existing if w.en.strip()}

    added, skipped = 0, 0
    now = time.time()

    for d in new_entries:
        if not isinstance(d, dict):
            continue
        en = str(d.get("en", "")).strip()
        zh = str(d.get("zh", "")).strip()
        if not en or not zh:
            continue
        key = normalize_en(en)
        if not key:
            continue
        src = str(d.get("src", "")).strip()
        category = str(d.get("category", "Unknown")).strip() or "Unknown"

        if key in by_key:
            prev = by_key[key]
            updated = WordEntry(
                en=prev.en or en,
                zh=zh or prev.zh,
                src=src or prev.src,
                category=category or prev.category,
                state=prev.state,
                seen_count=prev.seen_count,
                updated_at=now,
            )
            by_key[key] = updated
            skipped += 1
        else:
            by_key[key] = WordEntry(
                en=en,
                zh=zh,
                src=src,
                category=category,
                state="unseen",
                seen_count=0,
                updated_at=now,
            )
            added += 1

    merged_words = sorted(by_key.values(), key=lambda w: normalize_en(w.en))
    updated_bank = dict(bank)
    updated_bank["words"] = [w.to_json() for w in merged_words]
    return updated_bank, added, skipped


def set_state(bank: Dict[str, Any], en: str, state: WordState) -> Dict[str, Any]:
    key = normalize_en(en)
    words = list_words(bank)
    now = time.time()
    updated: List[WordEntry] = []
    for w in words:
        if normalize_en(w.en) == key:
            seen_count = w.seen_count + (1 if (w.state == "unseen" and state in ("seen", "mastered", "not_mastered")) else 0)
            updated.append(
                WordEntry(
                    en=w.en,
                    zh=w.zh,
                    src=w.src,
                    category=w.category,
                    state=state,
                    seen_count=seen_count,
                    updated_at=now,
                )
            )
        else:
            updated.append(w)
    out = dict(bank)
    out["words"] = [w.to_json() for w in updated]
    return out


def mark_seen(bank: Dict[str, Any], en: str) -> Dict[str, Any]:
    key = normalize_en(en)
    words = list_words(bank)
    now = time.time()
    updated: List[WordEntry] = []
    for w in words:
        if normalize_en(w.en) == key and w.state == "unseen":
            updated.append(
                WordEntry(
                    en=w.en,
                    zh=w.zh,
                    src=w.src,
                    category=w.category,
                    state="seen",
                    seen_count=w.seen_count + 1,
                    updated_at=now,
                )
            )
        else:
            updated.append(w)
    out = dict(bank)
    out["words"] = [w.to_json() for w in updated]
    return out


def reset_to_unseen(bank: Dict[str, Any], en: str) -> Dict[str, Any]:
    key = normalize_en(en)
    words = list_words(bank)
    now = time.time()
    updated: List[WordEntry] = []
    for w in words:
        if normalize_en(w.en) == key:
            updated.append(
                WordEntry(
                    en=w.en,
                    zh=w.zh,
                    src=w.src,
                    category=w.category,
                    state="unseen",
                    seen_count=w.seen_count,
                    updated_at=now,
                )
            )
        else:
            updated.append(w)
    out = dict(bank)
    out["words"] = [w.to_json() for w in updated]
    return out


def active_study_words(words: Iterable[WordEntry]) -> List[WordEntry]:
    return [w for w in words if w.state in ("unseen", "seen")]

