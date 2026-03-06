import re
import fitz

HEADER_TOP = 110
SKIP_TEXT = {"单词/短语", "中文释义", "来源"}
Y_ALIGN_TOL = 6


def get_category(page):
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for line in b["lines"]:
            x0, top = line["bbox"][0], line["bbox"][1]
            if x0 > 400 and top < 90:
                text = "".join(s["text"] for s in line["spans"]).strip()
                return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return "Unknown"


def detect_columns(page):
    """Detect column x0 boundaries from header row."""
    positions = {}
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for line in b["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text in ("单词/短语", "中文释义", "来源"):
                positions[text] = line["bbox"][0]
    if len(positions) == 3:
        x_en = positions["单词/短语"]
        x_zh = positions["中文释义"]
        x_src = positions["来源"]
        return (x_en - 5, x_zh - 5), (x_zh - 5, x_src - 5), (x_src - 5, x_src + 200)
    return (80, 235), (235, 390), (390, 560)


def is_cjk(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def extract_lines(page, col_en, col_zh, col_src):
    rows = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for line in b["lines"]:
            x0, top = line["bbox"][0], line["bbox"][1]
            if top < HEADER_TOP:
                continue
            text = "".join(s["text"] for s in line["spans"]).strip()
            if not text or text in SKIP_TEXT:
                continue
            if col_en[0] <= x0 < col_en[1]:
                col = "en"
            elif col_zh[0] <= x0 < col_zh[1]:
                col = "zh"
            elif col_src[0] <= x0 < col_src[1]:
                col = "src"
            else:
                continue
            # Sanity: en col should not be pure CJK, zh col should not be pure ASCII
            if col == "en" and is_cjk(text) and not any(c.isascii() and c.isalpha() for c in text):
                col = "zh"
            elif col == "zh" and not is_cjk(text) and re.match(r"^[\w\s\-]+$", text):
                col = "en"
            rows.append({"col": col, "top": top, "text": text})
    return sorted(rows, key=lambda r: r["top"])


def align_rows(lines):
    en_lines = [r for r in lines if r["col"] == "en"]
    zh_lines = [r for r in lines if r["col"] == "zh"]
    src_lines = [r for r in lines if r["col"] == "src"]

    def closest_unused(target, pool, used):
        best, best_d = None, float("inf")
        for i, r in enumerate(pool):
            if i in used:
                continue
            d = abs(r["top"] - target)
            if d < best_d and d <= Y_ALIGN_TOL:
                best, best_d = i, d
        return best

    used_zh, used_src = set(), set()
    entries = []

    for en in en_lines:
        zi = closest_unused(en["top"], zh_lines, used_zh)
        si = closest_unused(en["top"], src_lines, used_src)
        zh_text = zh_lines[zi]["text"] if zi is not None else ""
        src_text = src_lines[si]["text"] if si is not None else ""
        if zi is not None:
            used_zh.add(zi)
        if si is not None:
            used_src.add(si)
        entries.append({"en": en["text"], "zh": zh_text, "src": src_text, "top": en["top"]})

    for i, r in enumerate(src_lines):
        if i in used_src:
            continue
        for entry in reversed(entries):
            if entry["top"] < r["top"]:
                entry["src"] = (entry["src"] + " " + r["text"]).strip()
                break
        used_src.add(i)

    return entries


def merge_split_phrases(entries):
    merged, i = [], 0
    while i < len(entries):
        e = entries[i]
        if e["en"].endswith("-") and i + 1 < len(entries) and not entries[i + 1]["zh"]:
            e["en"] = e["en"][:-1] + entries[i + 1]["en"]
            e["src"] = (e["src"] + " " + entries[i + 1]["src"]).strip()
            i += 2
        else:
            i += 1
        merged.append(e)
    return merged


def parse_pdf(path):
    all_entries = []
    with fitz.open(path) as doc:
        for page in doc:
            category = get_category(page)
            col_en, col_zh, col_src = detect_columns(page)
            lines = extract_lines(page, col_en, col_zh, col_src)
            entries = align_rows(lines)
            entries = merge_split_phrases(entries)
            for e in entries:
                all_entries.append(
                    {
                        "en": e["en"],
                        "zh": e["zh"],
                        "src": e["src"],
                        "category": category,
                    }
                )

    seen, unique = set(), []
    for e in all_entries:
        key = e["en"].lower().strip()
        if not key or not e["zh"]:
            continue
        if is_cjk(key) or not any(c.isalpha() for c in key):
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)
    return unique

