"""Sửa tất định các lỗi chặn mà Quality Gate chỉ báo (không gọi LLM, không bịa số).

Mỗi hàm trả (văn bản mới, danh sách thay đổi đã làm); không sửa được thì giữ nguyên văn bản.
- `repair_chart_regions`: biểu đồ trộn WT/TC/ET → giữ một vùng (không tách chart để không lệch số Figure).
- `redact_untraced_chart_points`: điểm số UNTRACED trong ```chart → null; series rỗng bị bỏ; chart rỗng bị bỏ hẳn (lùi số hình).
- `repair_ledger_claims`: bỏ cụm 'missing-modality configuration(s)' khi sổ cái không có nhóm missing-modality.
- `add_uncited_corpus`: kho nhỏ phải cite hết → liệt kê tiêu đề paper chưa cite kèm [k] (chỉ mệnh đề sự thật).
- `drop_duplicate_charts`: hai biểu đồ cùng dữ liệu (≥80% cặp (x, y) trùng) → bỏ biểu đồ sau, lùi số hình.
- `soften_promotional_claims`: Abstract/Conclusion dùng từ quảng cáo (rigorous, clinically reliable, replacing…) → hạ giọng tất định.
- `ensure_methodology_disclosure`: mục Review Methodology thiếu loại review / số bài / số record / giới hạn sàng lọc, RoB, GRADE
  → chèn đoạn 'Review type and limitations' từ số đếm thật của lần chạy.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agent.evidence.citation_validator import expand_citation_clusters
from app.agent.evidence.consistency_check import (
    _FIRST_NOUNS,
    _LEDGER_WORD_RE,
    _MISSING_CFG_RE,
    _NEGATION_RE,
    _SELF_REF_RE,
    check_ledger_claims,
)
from app.agent.evidence.coverage import full_coverage_applies, uncited_papers
from app.agent.evidence.quant_check import _REGION_CANON, _REGION_RE, check_chart_block
from app.agent.evidence.report_structure import (
    _FIG_FENCE_OPEN_RE,
    _FIG_REF_RE,
    _LOCATED_CITE_RE,
    _SENTENCE_RE,
    _split_fences,
)
from app.agent.evidence.traceability import UNTRACED

logger = logging.getLogger(__name__)

_BLOCK_RE = re.compile(r"```(table|chart)\s*\n(.*?)```", re.DOTALL)  # cùng cách đếm với extract_numeric_claims
_CHART_RE = re.compile(r"```chart\s*\n(.*?)```", re.DOTALL)
_REGION_ORDER = ("WT", "TC", "ET")
_REGION_NAMES = {"WT": "whole tumor (WT)", "TC": "tumor core (TC)", "ET": "enhancing tumor (ET)"}
# cụm nói số lượng vùng: 'three tumor sub-regions', 'all 3 regions', 'each of the three regions'
_REGION_COUNT_RE = re.compile(
    r"\b(?:(?:each|all|any)\s+of\s+)?(?:the\s+|all\s+)?(?:two|three|2|3|multiple|several|all)\s+"
    r"(?:(?:tumou?r|segmentation|glioma|sub-?tumou?r)\s+)?(?:sub-?regions|regions)\b",
    re.I,
)
_POINT_RE = re.compile(r"^series (\d+), point (\d+)$")
CHART_NOTE = " Values that could not be found verbatim in the retrieved passages of the cited sources were withdrawn."


def _regions_in(s: str) -> set[str]:
    return {_REGION_CANON.get(m.lower(), m.upper()) for m in _REGION_RE.findall(s)}


_GAP = "\u2063"  # đánh dấu chỗ phần tử bị xoá khỏi phép liệt kê


def _tidy_list(s: str) -> str:
    """Dọn dấu phẩy / 'and' / mạo từ thừa sau khi xoá một phần tử (đánh dấu bằng _GAP) khỏi phép liệt kê."""
    gap_rules = [
        (rf",\s*{_GAP}\s*(and|or)\b", r" \1"),
        (rf"\b(?:and|or)\s+(?:the\s+)?{_GAP}", ""),
        (rf"{_GAP}\s*,\s*", ""),
        (rf",\s*{_GAP}", ""),
        (_GAP, ""),
    ]
    for pattern, repl in gap_rules:
        s = re.sub(pattern, repl, s)
    rules = [
        (r"[ \t]{2,}", " "),
        (r"\(\s*[,;/]?\s*\)", ""),
        (r"\(\s*(?:,|and|or)\s+", "("),
        (r"\s*,\s*(?:and|or)?\s*\)", ")"),
        (r",\s*,", ","),
        (r",\s*(and|or)\s*,", ","),
        (r"\b(and|or)\s*,\s*(and|or)\b", r"\1"),
        (r"\b(and|or)\s+(and|or)\b", r"\2"),
        (r"\b(?:the|a|an)\s+(?=(?:and|or)\b|[,.;:)]|$)", ""),
        (r",?\s*\b(?:and|or)\s*(?=[.;:)!?]|$)", ""),
        (r"\b(of|for|with|including|across|on|in)\s*,\s*", r"\1 "),
        (r"(^|[(])\s*(?:and|or)\s+", r"\1"),
        (r"(^|[(])\s*,\s*", r"\1"),
        (r",\s*(?=[.;:)!?]|$)", ""),
        (r"\s+([,.;:)!?])", r"\1"),
        (r"\(\s+", "("),
        (r"[ \t]{2,}", " "),
    ]
    for pattern, repl in rules:
        s = re.sub(pattern, repl, s)
    return s.strip()


def _strip_regions(s: str, keep: str) -> str:
    """Xoá tên vùng khác `keep` khỏi caption/nhãn trục rồi dọn liệt kê."""
    out = _REGION_RE.sub(lambda m: m.group(0) if _REGION_CANON.get(m.group(0).lower(), m.group(0).upper()) == keep else _GAP, s)
    return _tidy_list(out) if out != s else s


def _pick_region(regions: list[str | None]) -> str | None:
    counts = {r: regions.count(r) for r in _REGION_ORDER}
    best = max(_REGION_ORDER, key=lambda r: (counts[r], -_REGION_ORDER.index(r)))
    return best if counts[best] else None


def _single_region(name: str) -> str | None:
    found = _regions_in(name)
    return next(iter(found)) if len(found) == 1 else None


def repair_chart_regions(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Biểu đồ trộn nhiều vùng WT/TC/ET → giữ series (hoặc nhãn) của vùng có nhiều phần tử nhất; hoà theo WT, TC, ET."""
    fixed: list[dict[str, Any]] = []

    def _sub(m: re.Match) -> str:
        raw = m.group(1)
        if not any("vùng" in p for p in check_chart_block(raw)):
            return m.group(0)
        try:
            spec = json.loads(raw)
        except ValueError:
            return m.group(0)
        series = spec.get("series") if isinstance(spec, dict) and isinstance(spec.get("series"), list) else None
        if not series:
            return m.group(0)
        series_regions = [_single_region(str(s.get("name", ""))) if isinstance(s, dict) else None for s in series]
        keep = _pick_region(series_regions)
        if keep:
            spec["series"] = [s for s, r in zip(series, series_regions, strict=True) if r == keep]
            for s in spec["series"]:
                s["name"] = _strip_regions(str(s.get("name", "")), keep) or str(s.get("name", ""))
        else:
            labels = spec.get("labels") if isinstance(spec.get("labels"), list) else []
            label_regions = [_single_region(str(lb)) for lb in labels]
            keep = _pick_region(label_regions)
            if not keep:
                logger.warning("Biểu đồ trộn vùng nhưng không xác định được vùng theo series/nhãn, giữ nguyên")
                return m.group(0)
            idx = [i for i, r in enumerate(label_regions) if r in (keep, None)]
            spec["labels"] = [labels[i] for i in idx]
            for s in series:
                if not isinstance(s, dict):
                    continue
                for key in ("values", "errors"):
                    if isinstance(s.get(key), list) and len(s[key]) == len(labels):
                        s[key] = [s[key][i] for i in idx]
        for key in ("caption", "y_label", "title"):
            if isinstance(spec.get(key), str):
                # 'three tumor sub-regions' sai sau khi chỉ giữ một vùng → thay bằng tên vùng được giữ
                counted = _REGION_COUNT_RE.sub(f"the {_REGION_NAMES[keep]} sub-region", spec[key])
                spec[key] = _strip_regions(counted, keep)
        note = f" Only the {_REGION_NAMES[keep]} region is shown."
        spec["caption"] = str(spec.get("caption", "")).rstrip() + note
        fixed.append({"region_kept": keep})
        return f"```chart\n{json.dumps(spec, ensure_ascii=False)}\n```"

    out = _CHART_RE.sub(_sub, text)
    if fixed:
        logger.warning("Sửa %d biểu đồ trộn nhiều vùng phân đoạn: giữ %s", len(fixed), [f["region_kept"] for f in fixed])
    return out, fixed


def _drop_figure_number(text: str, k: int) -> str:
    """Hình số k đã bị bỏ: xoá câu nhắc 'Figure k', lùi số các hình sau (số hình = thứ tự khối, như renderer)."""
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        parts = _SENTENCE_RE.split(line)
        kept = [p for p in parts if not any(int(r.group(2)) == k for r in _FIG_REF_RE.finditer(p))]
        line = " ".join(kept) if len(kept) != len(parts) else line
        line = _FIG_REF_RE.sub(lambda r: f"{r.group(1)} {int(r.group(2)) - 1}" if int(r.group(2)) > k else r.group(0), line)
        out.append(line)
    return "\n".join(out)


def redact_untraced_chart_points(text: str, records: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Điểm UNTRACED trong ```chart → null. `records` là kết quả `trace_claims` trên CHÍNH `text` này."""
    targets: dict[int, list[dict[str, Any]]] = {}
    for r in records:
        m = re.fullmatch(r"chart#(\d+)", str(r.get("block", "")))
        if r.get("status") == UNTRACED and m and _POINT_RE.match(str(r.get("location", ""))):
            targets.setdefault(int(m.group(1)), []).append(r)
    if not targets:
        return text, []
    removed: list[dict[str, Any]] = []
    emptied: list[tuple[int, int]] = []  # (vị trí trong văn bản kết quả, số hình gốc) của chart không còn series
    counter = 0
    pieces: list[str] = []
    pos = 0
    for m in _BLOCK_RE.finditer(text):
        counter += 1
        pieces.append(text[pos : m.start()])
        pos = m.end()
        replacement = m.group(0)
        if m.group(1) == "chart" and counter in targets:
            try:
                spec = json.loads(m.group(2))
            except ValueError:
                spec = None
            series = spec.get("series") if isinstance(spec, dict) and isinstance(spec.get("series"), list) else None
            if series:
                changed = 0
                for rec in targets[counter]:
                    s_no, v_no = (int(x) for x in _POINT_RE.match(rec["location"]).groups())
                    s = series[s_no - 1] if 0 < s_no <= len(series) else None
                    values = s.get("values") if isinstance(s, dict) else None
                    if not isinstance(values, list) or not 0 < v_no <= len(values):
                        continue
                    v = values[v_no - 1]
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(float(v) - float(rec["value"])) < 1e-9:
                        values[v_no - 1] = None
                        removed.append({"block": rec["block"], "location": rec["location"], "value": rec["value"], "cites": rec.get("cites", [])})
                        changed += 1
                if changed:
                    spec["series"] = [s for s in series if not (isinstance(s, dict) and all(v is None for v in s.get("values") or [None]))]
                    if not spec["series"]:
                        # số hình GỐC = thứ tự khối hình (chart/image/mermaid) trong văn bản ban đầu
                        fig_no = sum(1 for ln in text[: m.start()].split("\n") if _FIG_FENCE_OPEN_RE.match(ln)) + 1
                        emptied.append((len("".join(pieces)), fig_no))
                        replacement = ""  # không in ghi chú vào bài; điểm bị gỡ đã có trong `removed`/validation report
                    else:
                        caption = str(spec.get("caption", ""))
                        if CHART_NOTE.strip() not in caption:
                            spec["caption"] = caption.rstrip() + CHART_NOTE
                        replacement = f"```chart\n{json.dumps(spec, ensure_ascii=False)}\n```"
        pieces.append(replacement)
    pieces.append(text[pos:])
    out = "".join(pieces)
    # chart bị bỏ: bỏ nhãn '**Figure N:' ngay trên (đi từ cuối để vị trí không lệch), rồi mới xoá câu nhắc
    # và lùi số hình theo số GỐC, giảm dần (bỏ hình 3 trước hình 1 thì không lùi số hai lần)
    for at, _ in reversed(emptied):
        before = out[:at]
        label = re.search(r"(?:^|\n)\*\*(?:Figure|Fig\.)\s*\d+\s*[:.][^\n]*\n+$", before)
        if label:
            out = before[: label.start()] + ("\n" if label.group(0).startswith("\n") else "") + out[at:]
    for fig_no in sorted((k for _, k in emptied), reverse=True):
        out = _drop_figure_number(out, fig_no)
    if removed:
        logger.warning("Gỡ %d điểm số không truy vết được khỏi biểu đồ (đặt null); %d biểu đồ bị bỏ hẳn", len(removed), len(emptied))
    return out, removed


def repair_ledger_claims(text: str, missing_groups: int) -> tuple[str, list[str]]:
    """Sổ cái không có nhóm missing-modality → bỏ cụm 'missing-modality configuration(s)/…' khỏi câu khẳng định ledger."""
    if missing_groups > 0:
        return text, []
    head, sep, refs = text.partition("\n## References")
    fixed: list[str] = []

    def _fix_sentence(sentence: str) -> str:
        if not (_LEDGER_WORD_RE.search(sentence) and _MISSING_CFG_RE.search(sentence) and not _NEGATION_RE.search(sentence)):
            return sentence
        new = _tidy_list(_MISSING_CFG_RE.sub(_GAP, sentence))
        if _MISSING_CFG_RE.search(new) or len(re.findall(r"[A-Za-z]{3,}", new)) < 4:
            new = ""  # không giữ được câu có nghĩa → bỏ cả câu
        fixed.append(sentence.strip()[:140])
        return new

    # mọi khối ``` (kể cả ```python) giữ nguyên
    out = [chunk if is_code else _fix_chunk(chunk, _fix_sentence) for is_code, chunk in _split_fences(head)]
    new_text = "".join(out) + sep + refs
    if fixed:
        logger.warning("Bỏ cụm missing-modality khỏi %d câu nói về sổ cái (sổ cái không có nhóm missing-modality)", len(fixed))
        if check_ledger_claims(new_text, 0):
            logger.warning("Vẫn còn câu ledger/missing-modality sau khi sửa")
    return new_text, fixed


def _fix_chunk(chunk: str, fix) -> str:
    """Sửa từng câu bằng `fix`; bỏ qua heading '#' và dòng bảng '|'. Chỉ câu bị sửa mới bị dọn khoảng trắng (giữ hard-break '  \\n')."""
    lines = chunk.split("\n")
    for li, line in enumerate(lines):
        if line.lstrip().startswith(("#", "|")):
            continue
        parts = re.split(r"((?<=[.!?])[ \t]+)", line)  # [câu, khoảng cách, câu, ...]
        pieces: list[str] = []
        changed = False
        for i in range(0, len(parts), 2):
            sentence, gap = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
            new = fix(sentence)
            if new == sentence:
                pieces.append(sentence + gap)
                continue
            changed = True
            if new:
                pieces.append(new + gap)
        if changed:
            new_line = "".join(pieces)
            lines[li] = new_line if line != line.rstrip() else new_line.rstrip()
    return "\n".join(lines)


_RELATED_RE = re.compile(r"^##\s+(?:\d+\.?\s*)?.*\b(?:Related Work|Background|Taxonomy)\b.*$", re.I | re.M)


def add_uncited_corpus(text: str, citations: list[Any], catalog: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """Kho nhỏ (phủ trọn) còn paper chưa cite → chèn đoạn liệt kê tiêu đề + [k]. Chạy TRƯỚC khi đánh số lại [n]."""
    available = {getattr(c, "paper_id", None) for c in citations} - {None, ""}
    if not full_coverage_applies(len(available)):
        return text, []
    # cụm '[1, 2]' / '[3–3]' và '[3, Table 1]' đều là đã cite → đưa về marker đơn trước khi đếm
    singles = _LOCATED_CITE_RE.sub(lambda m: ", ".join(f"[{n}]" for n in re.findall(r"\d+", m.group(1))), text)
    missing = uncited_papers(citations, expand_citation_clusters(singles))
    if not missing:
        return text, []
    first: dict[str, int] = {}
    for i, c in enumerate(citations, start=1):
        first.setdefault(getattr(c, "paper_id", None) or "", i)
    items = []
    for pid in sorted(missing, key=lambda p: first[p]):  # số [k] tăng dần
        title = str((catalog.get(pid) or {}).get("title") or "").strip().rstrip(".") or "untitled corpus document"
        items.append(f"*{title}* [{first[pid]}]")
    para = (
        "**Additional corpus studies.** The analysed corpus also contains the following studies, which are not discussed "
        "individually above: " + "; ".join(items) + "."
    )
    insert_at = None
    m = _RELATED_RE.search(text)
    if m:
        nxt = re.compile(r"^##\s", re.M).search(text, m.end())
        insert_at = nxt.start() if nxt else None
    if insert_at is None:
        ref = text.find("\n## References")
        insert_at = ref + 1 if ref != -1 else len(text)
    before, after = text[:insert_at].rstrip("\n"), text[insert_at:].lstrip("\n")
    new_text = before + "\n\n" + para + "\n\n" + after if after else before + "\n\n" + para + "\n"
    logger.warning("Bổ sung đoạn liệt kê %d paper trong kho chưa được cite", len(missing))
    return new_text, missing


def _article(orig: str, word: str) -> str:
    """'a'/'an' theo âm đầu (gần đúng): 'an evidence', 'a unified', 'a one-shot'."""
    w = word.lower()
    vowel = (w[:1] in "aeio" and not w.startswith(("one", "eu"))) or (w.startswith("u") and not re.match(r"u(?:ni|s|ti|r)", w))
    art = "an" if vowel else "a"
    return art.capitalize() if orig[:1].isupper() else art


# (mẫu, thay thế): chỉ từ ngữ tự đánh giá/quảng cáo; số liệu, trích dẫn, tên riêng không bị đụng tới
_PROMO_RULES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"\b(a|an)\s+(?:rigorous|unprecedented|groundbreaking)(?:,\s*|\s+and\s+|\s+)(\w+)", re.I),
     lambda m: _article(m.group(1), m.group(2)) + " " + m.group(2)),
    (re.compile(r"\b(?:rigorous(?:ly)?|unprecedented|groundbreaking),?\s+", re.I), ""),
    (re.compile(r"\bclinically reliable\b", re.I), "clinically relevant"),
    (re.compile(r"\b(replac)(ing|es|e)\b(?=\s+(?:the\s+)?(?:single|existing|prior|previous))", re.I),
     lambda m: {"ing": "complementing", "es": "complements", "e": "complement"}[m.group(2).lower()]),
]
_PROMO_SECTION_RE = re.compile(r"^#{1,3}\s+(?:\d+\.?\s*)?(?:Abstract|Conclusions?)\b.*$", re.I | re.M)


def soften_promotional_claims(text: str) -> tuple[str, list[str]]:
    """Abstract/Conclusion: bỏ tự đánh giá 'rigorous'/'unprecedented', 'clinically reliable' → 'clinically relevant',
    'replacing prior frameworks' → 'complementing'. Bài tự nhận không sàng lọc thủ công/không chạy lại nên không được tự khen."""
    changed: list[str] = []
    out = text
    for h in reversed(list(_PROMO_SECTION_RE.finditer(text))):
        nxt = re.compile(r"^#{1,2}\s", re.M).search(out, h.end())
        end = nxt.start() if nxt else len(out)
        body = out[h.end() : end]
        new = body
        for pattern, repl in _PROMO_RULES:
            new = pattern.sub(repl, new)
        if new != body:
            changed.append(h.group(0).strip())
            out = out[: h.end()] + new + out[end:]
    if changed:
        logger.warning("Hạ giọng từ ngữ tự đánh giá ở: %s", changed)
    return out, changed


_KNOWLEDGE_RE = re.compile(r",?\s*to the best of our knowledge,?\s*", re.I)
_THE_FIRST_RE = re.compile(rf"\b(the)\s+first\s+(?=({_FIRST_NOUNS})\b)", re.I)
_FIRST_TO_RE = re.compile(r"\b(is|are|was|were)\s+the\s+first\s+to\s+(\w+)", re.I)


def _soften_sentence(sentence: str) -> str:
    if not _SELF_REF_RE.search(sentence) or _NEGATION_RE.search(sentence):
        return sentence
    out = _KNOWLEDGE_RE.sub(" ", sentence).lstrip()
    out = _THE_FIRST_RE.sub(lambda m: _article(m.group(1), m.group(2)) + " ", out)
    out = _FIRST_TO_RE.sub(lambda m: m.group(2), out)  # 'we are the first to propose' → 'we propose'
    out = re.sub(r"\s{2,}", " ", out)
    lead = len(sentence) - len(sentence.lstrip())
    return sentence[:lead] + (out[:1].upper() + out[1:] if sentence.lstrip()[:1].isupper() else out)


def soften_novelty_claims(text: str) -> tuple[str, list[str]]:
    """Bài tự nhận 'the first survey/framework…' / 'to the best of our knowledge … first' → bỏ, giữ nội dung đóng góp.
    Kho PDF cố định không chứng minh được 'đầu tiên'. Không đụng khối fence, References, câu phủ định hay câu nói về bài khác."""
    head, sep, refs = text.partition("\n## References")
    changed: list[str] = []

    def _fix(sentence: str) -> str:
        new = _soften_sentence(sentence)
        if new != sentence:
            changed.append(sentence.strip()[:140])
        return new

    # khối ```...``` (bảng/biểu đồ/mermaid) giữ nguyên
    pieces = re.split(r"(```.*?```)", head, flags=re.DOTALL)
    head = "".join(p if p.startswith("```") else _fix_chunk(p, _fix) for p in pieces)
    if changed:
        logger.warning("Bỏ tuyên bố 'đầu tiên' chưa kiểm chứng: %s", changed)
    return head + sep + refs, changed


DUPLICATE_MIN_POINTS = 4
DUPLICATE_OVERLAP = 0.8


def _xy_pairs(spec: Any) -> set[tuple[float, float]]:
    pairs: set[tuple[float, float]] = set()
    if not isinstance(spec, dict) or spec.get("type") not in ("scatter", "xyline", "line"):
        return pairs
    for s in spec.get("series") or []:
        if not isinstance(s, dict):
            continue
        xs, ys = s.get("x") or [], s.get("y") or s.get("values") or []
        for x, y in zip(xs, ys, strict=False):
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                pairs.add((round(float(x), 4), round(float(y), 4)))
    return pairs


def drop_duplicate_charts(text: str) -> tuple[str, list[int]]:
    """Biểu đồ sau trùng dữ liệu biểu đồ trước (chặng khác nhau tự sinh cùng một scatter) → bỏ khối, nhãn và câu nhắc; lùi số hình."""
    seen: list[set[tuple[float, float]]] = []
    drop: list[tuple[int, int, int]] = []  # (start, end, số hình gốc)
    for m in _CHART_RE.finditer(text):
        try:
            pairs = _xy_pairs(json.loads(m.group(1)))
        except ValueError:
            continue
        if len(pairs) >= DUPLICATE_MIN_POINTS:
            if any(len(pairs & old) >= DUPLICATE_OVERLAP * min(len(pairs), len(old)) for old in seen):
                fig_no = sum(1 for ln in text[: m.start()].split("\n") if _FIG_FENCE_OPEN_RE.match(ln)) + 1
                drop.append((m.start(), m.end(), fig_no))
                continue
            seen.append(pairs)
    if not drop:
        return text, []
    out = text
    for start, end, _ in reversed(drop):
        before = out[:start]
        label = re.search(r"(?:^|\n)\*\*(?:Figure|Fig\.)\s*\d+\s*[:.][^\n]*\n+$", before)
        if label:
            before = before[: label.start()] + ("\n" if label.group(0).startswith("\n") else "")
        out = before + out[end:]
    for _, _, fig_no in sorted(drop, key=lambda d: d[2], reverse=True):
        out = _drop_figure_number(out, fig_no)
    figs = [d[2] for d in drop]
    logger.warning("Bỏ %d biểu đồ trùng dữ liệu với biểu đồ trước: Figure %s", len(drop), figs)
    return re.sub(r"\n{3,}", "\n\n", out), figs


_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_METHOD_H2_RE = re.compile(r"^##\s+(?:\d+\.\s*)?[^\n]*\b(?:Review Methodology|Methodology|Methods?)\b[^\n]*$", re.I | re.M)
_NEXT_HEAD_RE = re.compile(r"^#{2,3}\s", re.M)


def ensure_methodology_disclosure(text: str, n_cited: int, n_records: int, n_with_records: int) -> tuple[str, list[str]]:
    """Mục Review Methodology (khi KHÔNG có protocol người dùng khai báo) phải tự nêu: narrative review, số bài, số record/số bài
    có số liệu, không sàng lọc độc lập, không RoB/GRADE. Thiếu ý nào → chèn câu tương ứng (số đếm thật) sau đoạn mở đầu mục."""
    head = _METHOD_H2_RE.search(text)
    if not head:
        return text, []
    nxt = re.search(r"^##\s", text[head.end():], re.M)
    sec_end = head.end() + nxt.start() if nxt else len(text)
    section = _FENCE_RE.sub("", text[head.end():sec_end])
    missing: list[tuple[str, str]] = []
    if not re.search(r"\bnarrative\b", section, re.I):
        missing.append(("narrative", "This article is a narrative review of a curated corpus, not a systematic review."))
    if not re.search(rf"\b{n_cited}\s+(?:[\w-]+\s+){{0,3}}(?:papers|studies|articles|works|publications)\b", section, re.I):
        missing.append(("papers", f"It synthesizes {n_cited} cited papers."))
    if not re.search(r"\brecords?\b", section, re.I):
        missing.append((
            "records",
            f"{n_records} quantitative result records were extracted from {n_with_records} of these papers; the remaining papers contribute qualitative evidence only."
            if n_records else "No quantitative result record could be extracted, so the synthesis is qualitative.",
        ))
    if not re.search(r"screen", section, re.I):
        missing.append(("screening", "No independent title/abstract or full-text screening by two reviewers was performed; inclusion followed retrieval relevance."))
    if not (re.search(r"risk[- ]of[- ]bias", section, re.I) and re.search(r"\bGRADE\b", section)):
        missing.append(("rob_grade", "No formal risk-of-bias assessment and no GRADE certainty-of-evidence rating were performed, so conclusions are descriptive."))
    if not missing:
        return text, []
    para = "**Review type and limitations.** " + " ".join(sentence for _, sentence in missing)
    sub = _NEXT_HEAD_RE.search(text, head.end() + 1)
    at = sub.start() if sub and sub.start() < sec_end else sec_end
    insert = text[:at].rstrip() + "\n\n" + para + "\n\n"
    logger.warning("Bổ sung mô tả phương pháp còn thiếu: %s", [k for k, _ in missing])
    return insert + text[at:].lstrip("\n"), [k for k, _ in missing]
