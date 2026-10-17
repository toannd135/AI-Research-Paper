"""Nhận diện ngôn ngữ của người dùng để toàn bộ bài báo (văn bản, caption, nhãn hình) dùng đúng một ngôn ngữ.

Không phụ thuộc thư viện ngoài: chữ viết riêng (Hàn/Nhật/Trung/Nga/Ả Rập/Thái/Hindi), dấu tiếng Việt đặc trưng,
và điểm stopword cho các ngôn ngữ Latinh phổ biến. Mặc định 'en'.
"""

from __future__ import annotations

import re

LANGUAGE_NAMES = {
    "en": "English", "vi": "Vietnamese", "fr": "French", "es": "Spanish", "de": "German",
    "pt": "Portuguese", "it": "Italian", "id": "Indonesian", "ru": "Russian", "zh": "Chinese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic", "th": "Thai", "hi": "Hindi",
}

_SCRIPTS = [
    ("ko", re.compile(r"[가-힯ᄀ-ᇿ]")),
    ("ja", re.compile(r"[぀-ヿ]")),
    ("zh", re.compile(r"[一-鿿]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")),
    ("ar", re.compile(r"[؀-ۿ]")),
    ("th", re.compile(r"[฀-๿]")),
    ("hi", re.compile(r"[ऀ-ॿ]")),
]
# Ký tự gần như chỉ có trong tiếng Việt (phân biệt với Pháp/Bồ Đào Nha, vốn cũng có à á â ê ô ...).
_VI_DISTINCT = re.compile(r"[ạảãậẩẫắằặẳẵẹẻẽệểễịỉĩọỏõộổỗơớờợởỡụủũưứừựửữỳỵỷỹđ]", re.I)

_STOPWORDS = {
    "en": "the of and to in is for that with on as are by this from be an or which we",
    "fr": "le la les des du de et en un une est pour que dans sur avec par au aux ce qui",
    "es": "el la los las de y en un una es para que con por del al se como más su",
    "de": "der die das und ist von zu den mit für auf nicht ein eine im dem des auch",
    "pt": "o a os as de e em um uma é para que com por do da dos das não se mais",
    "it": "il lo la i gli le di e in un una è per che con del della dei non si più",
    "id": "yang dan di ke dari untuk dengan pada ini itu adalah dalam tidak akan atau juga",
}
_STOP_SETS = {k: set(v.split()) for k, v in _STOPWORDS.items()}
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str) -> str:
    """Trả về mã ISO 639-1 (xem LANGUAGE_NAMES); mặc định 'en' khi không đủ tín hiệu."""
    sample = text[:4000]
    letters = sum(c.isalpha() for c in sample)
    if letters == 0:
        return "en"
    for code, rx in _SCRIPTS:
        hits = len(rx.findall(sample))
        if hits / letters > 0.2:
            return "ja" if code == "zh" and re.search(r"[぀-ヿ]", sample) else code
    if len(_VI_DISTINCT.findall(sample)) >= 2 and len(_VI_DISTINCT.findall(sample)) / letters > 0.01:
        return "vi"
    words = [w.lower() for w in _WORD_RE.findall(sample)]
    if not words:
        return "en"
    scores = {k: sum(w in s for w in words) for k, s in _STOP_SETS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def language_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(code or "en", "English")


def is_foreign_paragraph(paragraph: str, target: str, min_words: int = 12) -> bool:
    """Đoạn đủ dài mà ngôn ngữ nhận diện khác ngôn ngữ đích → coi là lẫn ngôn ngữ."""
    if len(_WORD_RE.findall(paragraph)) < min_words and not any(rx.search(paragraph) for _, rx in _SCRIPTS):
        return False
    return detect_language(paragraph) != target
