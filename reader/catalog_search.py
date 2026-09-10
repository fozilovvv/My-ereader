"""Поиск книг в каталоге Project Gutenberg.

Каталог хранится у нас в базе — его наполняет команда sync_catalog.
Почему не обращаться к внешнему интерфейсу на каждый запрос: публичный
поиск Gutendex отвечает около ста секунд, а по локальной таблице ответ
приходит мгновенно и не зависит от того, доступен ли сейчас сервис.

Сам файл книги скачивается по требованию, уже после выбора.
"""
from . import search
from .models import Book, CatalogEntry

MAX_RESULTS = 24


def find(query: str, language: str = '') -> list:
    """Ищет по названию и автору. Каждое слово запроса должно найтись."""
    words = search.terms(query)
    if not words:
        return []

    entries = CatalogEntry.objects.all()
    for word in words:
        entries = entries.filter(search_text__contains=word)
    if language:
        entries = entries.filter(language=language)

    # Короткие названия выводим первыми: точное совпадение обычно короче
    # разных «...: with an introduction by...» и сборников.
    return list(entries.order_by('title')[:MAX_RESULTS])


def mark_existing(entries: list) -> list:
    """Помечает записи, книги по которым уже стоят в библиотеке.

    Сравниваем по поисковой строке — она уже приведена к нижнему регистру
    и одинаково собрана и у книги, и у записи каталога.
    """
    if not entries:
        return []

    library = set(Book.objects.values_list('search_text', flat=True))
    results = []

    for entry in entries:
        needle = search.normalize(entry.title)
        results.append({
            'entry': entry,
            'in_library': any(needle and needle in text for text in library),
        })
    return results


def languages_in_catalog() -> list:
    """Языки, которые реально встречаются в каталоге — для фильтра."""
    counts = {}
    for code in CatalogEntry.objects.values_list('language', flat=True):
        code = (code or '').strip()
        if code:
            counts[code] = counts.get(code, 0) + 1

    popular = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    return [{'code': code, 'count': count} for code, count in popular[:8]]
