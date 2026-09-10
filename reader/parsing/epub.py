"""Разбор EPUB.

EPUB — это обычный ZIP-архив со строгой структурой внутри:

    META-INF/container.xml   ← указывает, где лежит «паспорт» книги
    OEBPS/content.opf        ← паспорт: метаданные, список файлов, порядок чтения
    OEBPS/chapter1.xhtml     ← сам текст
    OEBPS/cover.jpg

Поэтому распаковываем стандартным zipfile и читаем XML стандартным
ElementTree — никаких сторонних библиотек не нужно.
"""
import io
import posixpath
import zipfile
from urllib.parse import unquote
from xml.etree import ElementTree

from .heading_rules import looks_like_chapter
from .sanitizer import has_text, split_html

CONTAINER_PATH = 'META-INF/container.xml'

NS = {
    'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
}


class EpubError(Exception):
    """Архив не похож на корректный EPUB."""


# --- вспомогательные функции ------------------------------------------

def _open(raw: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as error:
        raise EpubError('Файл не является ZIP-архивом (EPUB повреждён).') from error


def _find_opf(archive: zipfile.ZipFile) -> str:
    """Шаг 1: из container.xml узнаём путь до .opf — «паспорта» книги."""
    try:
        container = ElementTree.fromstring(archive.read(CONTAINER_PATH))
    except KeyError as error:
        raise EpubError('В архиве нет META-INF/container.xml.') from error

    rootfile = container.find('.//container:rootfile', NS)
    if rootfile is None or not rootfile.get('full-path'):
        raise EpubError('В container.xml не указан путь до OPF-файла.') from None
    return rootfile.get('full-path')


def _read_manifest(opf: ElementTree.Element) -> dict[str, dict]:
    """Манифест: id файла → {href, тип, свойства}. Это оглавление архива."""
    manifest = {}
    for item in opf.findall('.//opf:manifest/opf:item', NS):
        item_id = item.get('id')
        if item_id:
            manifest[item_id] = {
                'href': unquote(item.get('href', '')),
                'type': item.get('media-type', ''),
                'properties': item.get('properties', ''),
            }
    return manifest


def _spine_order(opf: ElementTree.Element) -> list[str]:
    """Spine («корешок») задаёт порядок чтения — то, что нам и нужно."""
    return [
        ref.get('idref')
        for ref in opf.findall('.//opf:spine/opf:itemref', NS)
        if ref.get('idref')
    ]


def _load_opf(archive: zipfile.ZipFile):
    opf_path = _find_opf(archive)
    opf = ElementTree.fromstring(archive.read(opf_path))
    return opf, posixpath.dirname(opf_path)


def _resolve(base: str, href: str) -> str:
    """Пути внутри OPF относительны — превращаем их в путь внутри архива."""
    return posixpath.normpath(posixpath.join(base, href)) if base else href


# --- основные функции --------------------------------------------------

def parse_epub(raw: bytes) -> list[dict]:
    """Возвращает главы в порядке чтения.

    Обычно один файл spine — это одна глава. Но некоторые издания (часто
    встречается на Project Gutenberg) складывают в один файл сразу
    несколько глав подряд, отделяя их только заголовками вида
    «CHAPTER XX.» внутри текста, без разбивки на отдельные файлы.
    split_html умеет резать такой файл на настоящие главы — см. sanitizer.py.
    """
    chapters = []
    with _open(raw) as archive:
        opf, base = _load_opf(archive)
        manifest = _read_manifest(opf)

        for idref in _spine_order(opf):
            item = manifest.get(idref)
            if item is None or 'html' not in item['type']:
                continue
            try:
                source = archive.read(_resolve(base, item['href']))
            except KeyError:
                continue  # файл заявлен в манифесте, но отсутствует — пропускаем

            text = source.decode('utf-8', errors='replace')
            for segment in split_html(text, looks_like_chapter):
                if not has_text(segment['content']):
                    continue  # пустые страницы-разделители не нужны

                # Безымянный кусок в начале разрезанного файла — это хвост
                # предыдущей главы (обычно вклейка с иллюстрацией). Дописываем
                # его туда, а не заводим в оглавлении пустышку «Глава 12».
                if segment['continuation'] and chapters:
                    chapters[-1]['content'] += '\n' + segment['content']
                    continue

                chapters.append({
                    'title': segment['title'] or f'Глава {len(chapters) + 1}',
                    'content': segment['content'],
                })

    if not chapters:
        raise EpubError('В EPUB не найдено ни одной текстовой главы.')
    return chapters


def extract_metadata(raw: bytes) -> dict:
    """Достаёт название, автора, язык, аннотацию и обложку."""
    with _open(raw) as archive:
        opf, base = _load_opf(archive)
        manifest = _read_manifest(opf)

        def text_of(path: str) -> str:
            node = opf.find(path, NS)
            return (node.text or '').strip() if node is not None else ''

        authors = [
            (node.text or '').strip()
            for node in opf.findall('.//dc:creator', NS)
            if (node.text or '').strip()
        ]

        # Жанры: в EPUB их складывают в dc:subject, иногда десятками.
        subjects = [
            (node.text or '').strip()
            for node in opf.findall('.//dc:subject', NS)
            if (node.text or '').strip()
        ]

        data = {
            'subjects': subjects,
            'title': text_of('.//dc:title'),
            'author': ', '.join(authors),
            'language': text_of('.//dc:language')[:10],
            'description': text_of('.//dc:description'),
        }

        cover_href = _find_cover_href(opf, manifest)
        if cover_href:
            try:
                data['cover_name'] = posixpath.basename(cover_href)
                data['cover_bytes'] = archive.read(_resolve(base, cover_href))
            except KeyError:
                data.pop('cover_name', None)

    return data


def _find_cover_href(opf: ElementTree.Element, manifest: dict) -> str:
    """Обложку помечают двумя разными способами — проверяем оба."""
    # EPUB 3: у элемента манифеста properties="cover-image"
    for item in manifest.values():
        if 'cover-image' in item['properties']:
            return item['href']

    # EPUB 2: <meta name="cover" content="id-обложки"/>
    for meta in opf.findall('.//opf:metadata/opf:meta', NS):
        if meta.get('name') == 'cover':
            item = manifest.get(meta.get('content', ''))
            if item:
                return item['href']
    return ''
