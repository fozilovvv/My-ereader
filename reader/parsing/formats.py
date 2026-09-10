"""Разбор конкретных форматов файлов в список глав.

Каждая функция-парсер принимает сырые байты файла и возвращает список словарей:
    [{'title': 'Глава 1', 'content': '<p>...</p>'}, ...]
"""
from html import escape

from .heading_rules import looks_like_chapter

# Если в файле нет заголовков, режем текст на куски примерно такого размера.
MAX_CHARS_PER_CHAPTER = 20_000

# Порядок важен: сначала пробуем строгий UTF-8, потом самую частую «старую» кодировку.
ENCODINGS = ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1')


def _decode(raw: bytes) -> str:
    """Превращает байты в строку, подбирая кодировку."""
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def _to_html(paragraphs: list[str]) -> str:
    """Список абзацев → безопасный HTML. escape() гасит любые < и > из текста."""
    return '\n'.join(f'<p>{escape(p)}</p>' for p in paragraphs)


def _chunk(paragraphs: list[str], limit: int) -> list[list[str]]:
    """Режет длинный список абзацев на куски, не разрывая абзацы."""
    chunks, current, size = [], [], 0
    for paragraph in paragraphs:
        if current and size + len(paragraph) > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(paragraph)
        size += len(paragraph)
    if current:
        chunks.append(current)
    return chunks


def parse_txt(raw: bytes) -> list[dict]:
    """Разбирает обычный текстовый файл.

    Логика: пустая строка = конец абзаца, строка вида «Глава 5» = начало главы.
    Если заголовков не нашлось, книга режется на куски по размеру.
    """
    text = _decode(raw).replace('\r\n', '\n').replace('\r', '\n')

    raw_chapters: list[tuple[str, list[str]]] = []
    title = ''
    paragraphs: list[str] = []
    buffer: list[str] = []

    for line in text.split('\n'):
        stripped = line.strip()

        if not stripped:                       # пустая строка — абзац закончился
            if buffer:
                paragraphs.append(' '.join(buffer))
                buffer = []
            continue

        if looks_like_chapter(stripped):        # нашли заголовок — закрываем главу
            if buffer:
                paragraphs.append(' '.join(buffer))
                buffer = []
            if paragraphs:
                raw_chapters.append((title, paragraphs))
                paragraphs = []
            title = stripped
            continue

        buffer.append(stripped)                # обычная строка текста

    if buffer:
        paragraphs.append(' '.join(buffer))
    if paragraphs:
        raw_chapters.append((title, paragraphs))

    chapters = []
    for chapter_title, chapter_paragraphs in raw_chapters:
        pieces = _chunk(chapter_paragraphs, MAX_CHARS_PER_CHAPTER)
        for index, piece in enumerate(pieces):
            chapters.append({
                'title': chapter_title if index == 0 else f'{chapter_title} (продолжение)'.strip(),
                'content': _to_html(piece),
            })
    return chapters
