"""Разбор FB2 (FictionBook 2.0).

FB2 проще EPUB: это один XML-файл, где текст размечен собственными тегами
(<section>, <p>, <emphasis>), а картинки лежат тут же в base64 внутри <binary>.
Наша задача — перевести теги FB2 в обычный HTML.
"""
import base64
import io
import zipfile
from html import escape
from xml.etree import ElementTree

FB2_NS = '{http://www.gribuser.ru/xml/fictionbook/2.0}'
XLINK_HREF = '{http://www.w3.org/1999/xlink}href'

# Теги FB2 → теги HTML
INLINE_MAP = {
    'emphasis': 'em',
    'strong': 'strong',
    'strikethrough': 's',
    'sub': 'sub',
    'sup': 'sup',
    'code': 'code',
}


class Fb2Error(Exception):
    """Файл не похож на корректный FB2."""


def _local(tag) -> str:
    """'{namespace}section' → 'section'."""
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _root(raw: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(raw)
    except ElementTree.ParseError as error:
        raise Fb2Error(f'Ошибка XML в FB2: {error}') from error


def _render(element: ElementTree.Element) -> str:
    """Рекурсивно превращает элемент FB2 в HTML."""
    tag = _local(element.tag)

    if tag in ('image', 'binary', 'title'):
        return ''  # обрабатываются отдельно

    inner = escape(element.text or '')
    for child in element:
        inner += _render(child)
        inner += escape(child.tail or '')

    if tag == 'p':
        return f'<p>{inner}</p>'
    if tag == 'empty-line':
        return '<br>'
    if tag == 'subtitle':
        return f'<h3>{inner}</h3>'
    if tag == 'v':                      # строка стихотворения
        return f'<p>{inner}</p>'
    if tag in ('cite', 'epigraph'):
        return f'<blockquote>{inner}</blockquote>'
    if tag in INLINE_MAP:
        html_tag = INLINE_MAP[tag]
        return f'<{html_tag}>{inner}</{html_tag}>'
    return inner                        # poem, stanza, annotation и прочие обёртки


def _section_title(section: ElementTree.Element) -> str:
    node = section.find(f'{FB2_NS}title')
    if node is None:
        return ''
    words = ' '.join(''.join(node.itertext()).split())
    return words[:255]


def _collect(section: ElementTree.Element, chapters: list[dict]) -> None:
    """Одна <section> = одна глава. Вложенные секции становятся отдельными главами."""
    parts, subsections = [], []

    for child in section:
        name = _local(child.tag)
        if name == 'title':
            continue
        if name == 'section':
            subsections.append(child)
            continue
        parts.append(_render(child))

    content = '\n'.join(part for part in parts if part.strip())
    if content:
        chapters.append({'title': _section_title(section), 'content': content})

    for subsection in subsections:
        _collect(subsection, chapters)


def parse_fb2(raw: bytes) -> list[dict]:
    root = _root(raw)
    chapters: list[dict] = []

    for body in root.findall(f'{FB2_NS}body'):
        if body.get('name') == 'notes':
            continue  # сноски — не главы
        sections = [child for child in body if _local(child.tag) == 'section']
        for section in sections or [body]:
            _collect(section, chapters)

    if not chapters:
        raise Fb2Error('В FB2 не найдено текстовых секций.')
    return chapters


def extract_metadata(raw: bytes) -> dict:
    root = _root(raw)
    info = root.find(f'{FB2_NS}description/{FB2_NS}title-info')
    if info is None:
        return {}

    def text_of(path: str) -> str:
        node = info.find(path)
        return (node.text or '').strip() if node is not None else ''

    authors = []
    for author in info.findall(f'{FB2_NS}author'):
        name = ' '.join(
            part.strip()
            for tag in ('first-name', 'middle-name', 'last-name')
            for part in [(author.findtext(f'{FB2_NS}{tag}') or '')]
            if part.strip()
        )
        if name:
            authors.append(name)

    genres = [
        (node.text or '').strip()
        for node in info.findall(f'{FB2_NS}genre')
        if (node.text or '').strip()
    ]

    annotation = info.find(f'{FB2_NS}annotation')
    data = {
        'subjects': genres,
        'title': text_of(f'{FB2_NS}book-title'),
        'author': ', '.join(authors),
        'language': text_of(f'{FB2_NS}lang')[:10],
        'description': ' '.join(''.join(annotation.itertext()).split()) if annotation is not None else '',
    }

    cover = info.find(f'{FB2_NS}coverpage/{FB2_NS}image')
    if cover is not None:
        cover_id = (cover.get(XLINK_HREF) or '').lstrip('#')
        for binary in root.findall(f'{FB2_NS}binary'):
            if binary.get('id') == cover_id and binary.text:
                try:
                    data['cover_bytes'] = base64.b64decode(binary.text)
                    data['cover_name'] = cover_id or 'cover.jpg'
                except (ValueError, TypeError):
                    pass
                break

    return data


# --- вариант «книга в zip-архиве» ---------------------------------------

def _unzip_fb2(raw: bytes) -> bytes:
    """Многие каталоги отдают книги как .fb2.zip — достаём файл изнутри."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if name.lower().endswith('.fb2'):
                    return archive.read(name)
    except zipfile.BadZipFile as error:
        raise Fb2Error('Архив повреждён.') from error
    raise Fb2Error('В архиве не найден .fb2-файл.')


def parse_fb2_zip(raw: bytes) -> list[dict]:
    return parse_fb2(_unzip_fb2(raw))


def extract_metadata_zip(raw: bytes) -> dict:
    return extract_metadata(_unzip_fb2(raw))
