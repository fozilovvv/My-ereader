"""Внешние источники книг: откуда библиотека берёт новые тексты.

Каждый источник отдаёт результаты в одном и том же виде, чтобы страница
поиска не знала, откуда именно пришла книга:

    {'kind', 'source', 'key', 'title', 'author', 'language', 'cover', 'note'}

kind = 'book'   — можно добавить в библиотеку
kind = 'author' — можно открыть список произведений

Оба источника легальны, книги в общественном достоянии:

* Project Gutenberg — каталог скачан целиком и лежит у нас в базе,
  поэтому поиск мгновенный (см. команду sync_catalog).
* Викитека — русская классика. Каталог целиком не выкачать, зато у неё
  быстрый программный интерфейс, поэтому ищем прямыми запросами.
"""
import json
import re
from urllib.parse import quote

from . import fetching, search
from .models import Book, CatalogEntry

GUTENBERG = 'gutenberg'
WIKISOURCE = 'wikisource'

SOURCES = [
    {'code': GUTENBERG, 'label': 'Project Gutenberg', 'hint': 'англоязычная классика'},
    {'code': WIKISOURCE, 'label': 'Викитека', 'hint': 'русская классика'},
]

MAX_RESULTS = 24
AUTHOR_WORKS_LIMIT = 60

API = 'https://ru.wikisource.org/w/api.php?format=json&'
WIKI_EXPORT = 'https://ws-export.wmcloud.org/?format=epub&lang=ru&page={page}'

# Пространство имён «Автор» на русской Викитеке. Номер именно 102:
# 106 — это «Индекс», сканы книг, а не страницы писателей.
AUTHOR_NAMESPACE = 102
AUTHOR_PREFIX = 'Автор:'

# Автор указан в скобках прямо в названии страницы: «Метель (Пушкин)»
AUTHOR_IN_TITLE = re.compile(r'\(([^)]+)\)')

# Названия частей: сами по себе «Том I» или «Часть 2» ничего не говорят,
# поэтому такие показываем вместе с названием произведения.
PART_TITLE = re.compile(r'^(том|часть|книга|глава|выпуск|vol|part)\b', re.I)

# Служебные страницы: указатели, оглавления, варианты в старой орфографии.
SERVICE_TITLE = re.compile(
    r'(^(указатель|список|индекс|категория|страница|словарь)\b'
    r'|оглавлени|содержани|/до($|/)|\bбиблиография\b)',
    re.I,
)


class SourceError(Exception):
    """Источник недоступен — понятная человеку причина."""


# --- Project Gutenberg -------------------------------------------------

def _search_gutenberg(query: str, language: str = '') -> list:
    words = search.terms(query)
    if not words:
        return []

    entries = CatalogEntry.objects.all()
    for word in words:
        entries = entries.filter(search_text__contains=word)
    if language:
        entries = entries.filter(language=language)

    return [
        {
            'kind': 'book',
            'source': GUTENBERG,
            'key': str(entry.gutenberg_id),
            'title': entry.title,
            'author': entry.authors,
            'language': entry.language,
            'cover': entry.cover_url,
            'note': f'#{entry.gutenberg_id}',
        }
        for entry in entries.order_by('title')[:MAX_RESULTS]
    ]


# --- Викитека ----------------------------------------------------------

def _api(params: str) -> dict:
    """Запрос к программному интерфейсу Викитеки."""
    try:
        raw, _ = fetching.fetch(API + params)
        return json.loads(raw.decode('utf-8'))
    except fetching.FetchError as error:
        raise SourceError(f'Викитека недоступна: {error}') from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SourceError('Викитека вернула неожиданный ответ.') from None


def _readable(page_title: str) -> tuple:
    """«Повести Белкина (Пушкин)/Метель» -> («Метель», «Пушкин»).

    В Викитеке название страницы несёт сразу и произведение, и сборник,
    и автора. Читателю нужно только произведение и имя писателя.
    """
    author = ''
    found = AUTHOR_IN_TITLE.search(page_title)
    if found:
        author = found.group(1).strip()

    # После последней косой черты — само произведение, до неё сборник.
    parent, _, leaf = page_title.rpartition('/')
    title = AUTHOR_IN_TITLE.sub('', leaf or page_title).strip(' —-–')

    # «Война и мир (Толстой)/Том I» -> «Война и мир — Том I».
    # Один только «Том I» ничего читателю не говорит, поэтому для частей
    # и томов возвращаем название вместе с родительским.
    if parent and PART_TITLE.match(title):
        head = AUTHOR_IN_TITLE.sub('', parent.rsplit('/', 1)[-1]).strip(' —-–')
        if head:
            title = f'{head} — {title}'

    return (title or page_title), author


def _is_service_page(page_title: str) -> bool:
    """Указатели, оглавления и дореформенные варианты книгами не считаем."""
    return bool(SERVICE_TITLE.search(page_title))


def _search_wikisource(query: str) -> list:
    """Поиск произведений по названию."""
    query = (query or '').strip()
    if len(query) < 2:
        return []

    payload = _api(f'action=query&list=search&srnamespace=0'
                   f'&srlimit={MAX_RESULTS * 2}&srsearch={quote(query)}')

    results = []
    for item in payload.get('query', {}).get('search', []):
        page = item.get('title', '')
        if not page or _is_service_page(page):
            continue

        title, author = _readable(page)
        results.append({
            'kind': 'book',
            'source': WIKISOURCE,
            'key': page,
            'title': title,
            'author': author,
            'language': 'ru',
            'cover': '',
            'note': 'Викитека',
        })
        if len(results) >= MAX_RESULTS:
            break
    return results


def _search_authors(query: str) -> list:
    """Поиск страниц писателей."""
    query = (query or '').strip()
    if len(query) < 2:
        return []

    payload = _api(f'action=query&list=search&srnamespace={AUTHOR_NAMESPACE}'
                   f'&srlimit={MAX_RESULTS}&srsearch={quote(query)}')

    results = []
    for item in payload.get('query', {}).get('search', []):
        page = item.get('title', '')
        if not page.startswith(AUTHOR_PREFIX):
            continue
        results.append({
            'kind': 'author',
            'source': WIKISOURCE,
            'key': page,
            'title': page[len(AUTHOR_PREFIX):],
            'author': '',
            'language': 'ru',
            'cover': '',
            'note': 'автор',
        })
    return results


def author_works(page: str, query: str = '') -> list:
    """Произведения со страницы писателя.

    Викитека держит их обычными ссылками на странице автора, поэтому
    спрашиваем именно ссылки: список приходит одним запросом за секунду.
    """
    payload = _api(f'action=parse&prop=links&page={quote(page)}')
    links = payload.get('parse', {}).get('links', [])

    words = search.terms(query)
    results = []

    for link in links:
        if link.get('ns') != 0 or 'exists' not in link:
            continue          # красные ссылки на несозданные страницы пропускаем

        page_title = link.get('*', '')
        if not page_title or _is_service_page(page_title):
            continue

        title, author = _readable(page_title)

        # Если внутри списка задан запрос — оставляем подходящее.
        if words:
            haystack = search.normalize(page_title)
            if not all(word in haystack for word in words):
                continue

        results.append({
            'kind': 'book',
            'source': WIKISOURCE,
            'key': page_title,
            'title': title,
            'author': author,
            'language': 'ru',
            'cover': '',
            'note': 'Викитека',
        })
        if len(results) >= AUTHOR_WORKS_LIMIT:
            break

    results.sort(key=lambda item: item['title'].lower())
    return results


def _wikisource_download(key: str) -> str:
    return WIKI_EXPORT.format(page=quote(key.replace(' ', '_')))


# --- Общий интерфейс ---------------------------------------------------

def find(source: str, query: str, language: str = '', mode: str = 'works') -> list:
    """Ищет в выбранном источнике. Результаты — одного вида для всех."""
    if source == WIKISOURCE:
        if mode == 'authors':
            return _search_authors(query)
        return _search_wikisource(query)
    return _search_gutenberg(query, language)


def download_url(source: str, key: str) -> str:
    """Прямая ссылка на файл книги в выбранном источнике."""
    if source == WIKISOURCE:
        return _wikisource_download(key)
    return f'https://www.gutenberg.org/cache/epub/{key}/pg{key}.epub'


def mark_existing(results: list) -> list:
    """Помечает то, что уже стоит в библиотеке, чтобы не добавлять дважды."""
    if not results:
        return []

    library = set(Book.objects.values_list('search_text', flat=True))
    for item in results:
        needle = search.normalize(item['title'])
        item['in_library'] = (
            item['kind'] == 'book'
            and bool(needle)
            and any(needle in text for text in library)
        )
    return results


def languages_in_catalog() -> list:
    """Языки каталога Gutenberg — для фильтра. У Викитеки язык всегда один."""
    counts = {}
    for code in CatalogEntry.objects.values_list('language', flat=True):
        code = (code or '').strip()
        if code:
            counts[code] = counts.get(code, 0) + 1

    popular = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    return [{'code': code, 'count': count} for code, count in popular[:8]]


# Частые запросы — чтобы не вспоминать точное написание имени страницы.
POPULAR_AUTHORS = [
    'Пушкин', 'Толстой', 'Достоевский', 'Чехов', 'Гоголь',
    'Лермонтов', 'Тургенев', 'Куприн', 'Некрасов', 'Бунин',
]
