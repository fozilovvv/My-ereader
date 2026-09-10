"""Правило «похоже ли это на начало главы» — общее для всех форматов.

TXT встречает эти заголовки как обычные строки текста, EPUB — как теги
<h1>–<h6> внутри HTML. Само правило узнавания у них одно и то же, поэтому
оно вынесено сюда и переиспользуется в formats.py и epub.py.
"""
import re

PATTERNS = (
    re.compile(r'^(глава|часть|книга|том|пролог|эпилог|chapter|part|prologue|epilogue)\b.{0,60}$', re.I),
    re.compile(r'^[IVXLCDM]{1,7}\.?$'),          # римские цифры: IV, XII
    re.compile(r'^\*\s*\*\s*\*$'),               # разделитель * * *
)


def looks_like_chapter(text: str) -> bool:
    """Похож ли текст заголовка на начало главы, а не на что-то другое?"""
    text = (text or '').strip()
    if not text or len(text) > 70:
        return False
    return any(pattern.match(text) for pattern in PATTERNS)
