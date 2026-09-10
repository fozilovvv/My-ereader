"""Конвейер импорта книги: файл → главы в базе данных."""
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from reader.models import Book, CatalogEntry, Category, Chapter, ReadingProgress

from reader import categorizing

from . import epub, fb2, formats
from .sanitizer import text_of
from .epub import EpubError
from .fb2 import Fb2Error


class ParseError(Exception):
    """Файл не удалось разобрать — понятная человеку причина."""


# Диспетчер: расширение файла → функция, режущая файл на главы.
PARSERS = {
    '.txt': formats.parse_txt,
    '.epub': epub.parse_epub,
    '.fb2': fb2.parse_fb2,
    '.zip': fb2.parse_fb2_zip,
}

# Не для каждого формата есть метаданные — у .txt их взять неоткуда.
METADATA_READERS = {
    '.epub': epub.extract_metadata,
    '.fb2': fb2.extract_metadata,
    '.zip': fb2.extract_metadata_zip,
}


def import_book(book: Book) -> int:
    """Читает файл книги, создаёт главы, обновляет статус. Возвращает число глав."""
    if not book.source_file:
        raise ParseError('У книги не загружен файл.')

    suffix = Path(book.source_file.name).suffix.lower()
    parser = PARSERS.get(suffix)
    if parser is None:
        supported = ', '.join(sorted(PARSERS))
        raise ParseError(f'Формат «{suffix}» пока не поддерживается. Доступно: {supported}')

    with book.source_file.open('rb') as file_handle:
        raw = file_handle.read()

    # Ошибки конкретных форматов переводим в единый ParseError,
    # чтобы вызывающему коду не нужно было знать про EPUB и FB2.
    try:
        chapters = parser(raw)
    except (EpubError, Fb2Error) as error:
        raise ParseError(str(error)) from error

    if not chapters:
        raise ParseError('В файле не найдено текста.')

    metadata = {}
    metadata_reader = METADATA_READERS.get(suffix)
    if metadata_reader:
        try:
            metadata = metadata_reader(raw) or {}
            _apply_metadata(book, metadata)
        except Exception:
            metadata = {}  # метаданные — бонус, из-за них импорт срывать нельзя

    # Цитаты привязаны к главам, а главы сейчас будут пересозданы.
    # Запоминаем их заранее, чтобы после пересборки вернуть привязку:
    # человек сохранял цитату не для того, чтобы потерять её при повторном разборе.
    saved_quotes = list(book.quotes.all())

    # То же и с прогрессом чтения. Здесь проще: порядковый номер главы
    # при повторном разборе того же файла не меняется, поэтому
    # запоминаем именно его, а не ссылку на объект.
    saved_positions = {
        progress.pk: progress.chapter.order
        for progress in book.progress_entries.select_related('chapter')
        if progress.chapter_id
    }

    # transaction.atomic: либо книга пересобралась целиком, либо база не изменилась.
    with transaction.atomic():
        book.chapters.all().delete()
        Chapter.objects.bulk_create([
            Chapter(
                book=book,
                order=index,
                title=chapter['title'][:255],
                content=chapter['content'],
                char_count=len(chapter['content']),
            )
            for index, chapter in enumerate(chapters)
        ])
        # Последний рубеж: метаданных не было (например, .txt) и название
        # не ввели руками — тогда берём имя файла.
        if not book.title:
            book.title = Path(book.source_file.name).stem[:255]

        book.total_chars = sum(len(chapter['content']) for chapter in chapters)
        book.status = Book.Status.READY
        book.parse_error = ''
        book.save()

        # Категории — связь «многие ко многим»: записать её можно только
        # после save(), до этого у книги ещё нет первичного ключа.
        apply_categories(book, metadata.get('subjects', []))

        relink_quotes(book, saved_quotes)
        relink_progress(book, saved_positions)

    return len(chapters)


def relink_quotes(book: Book, quotes: list) -> int:
    """Возвращает цитатам ссылку на главу, находя их текст в новых главах.

    Сравниваем не HTML, а очищенный текст: разметка при пересборке могла
    измениться, а слова остались теми же.
    """
    if not quotes:
        return 0

    # Текст каждой главы готовим один раз: цитат может быть много.
    plain = [(chapter, text_of(chapter.content)) for chapter in book.chapters.all()]
    restored = 0

    for quote in quotes:
        needle = ' '.join(quote.text.split())[:200]
        if not needle:
            continue
        for chapter, content in plain:
            if needle in content:
                if quote.chapter_id != chapter.pk:
                    quote.chapter = chapter
                    quote.save(update_fields=['chapter'])
                restored += 1
                break

    return restored


# Имя файла с Gutenberg несёт номер книги: pg1342.epub, pg84-images-3.epub
GUTENBERG_FILE = re.compile(r'^pg(\d+)')


def catalog_subjects(book: Book) -> list:
    """Темы из локального каталога Gutenberg — когда в самом файле их нет.

    Номер книги записан в имени файла, а каталог уже лежит у нас в базе
    (см. команду sync_catalog), поэтому обращаться в сеть не нужно.
    """
    match = GUTENBERG_FILE.match(Path(book.source_file.name).name)
    if not match:
        return []

    entry = CatalogEntry.objects.filter(gutenberg_id=int(match.group(1))).first()
    if entry is None:
        return []
    return [part.strip() for part in entry.subjects.split(';') if part.strip()]


def apply_categories(book: Book, subjects: list) -> list:
    """Расставляет жанры по метаданным файла. Уже заданные не трогает."""
    if book.categories.exists():
        return []

    # В части файлов поле жанров пустое — тогда спрашиваем каталог.
    if not subjects:
        subjects = catalog_subjects(book)
    if not subjects:
        return []

    codes = categorizing.match(subjects)
    if not codes:
        return []

    # Жанр берём на языке самой книги: английский роман попадёт в «Classics»,
    # русский — в «Классику». Язык книги приходит из её же метаданных.
    # Для прочих языков (немецкий, португальский) берём английский набор —
    # он ближе читателю такой книги, чем русский.
    language = (book.language or '').lower()[:2]
    if language != Category.Language.RU:
        language = Category.Language.EN

    # Только заведённые в справочнике: выдумывать новые на лету не нужно,
    # иначе список расползётся от разнобоя в чужих файлах.
    found = list(Category.objects.filter(code__in=codes, language=language))
    book.categories.add(*found)
    return [category.name for category in found]


def _apply_metadata(book: Book, data: dict) -> None:
    """Заполняет пустые поля книги данными из файла. Введённое руками — не трогает."""
    title = (data.get('title') or '').strip()
    if title and not book.title:
        book.title = title[:255]
        book.slug = ''          # адрес пересоберётся под новое название в Book.save()

    for field in ('author', 'description'):
        value = (data.get(field) or '').strip()
        if field == 'author':
            value = _clean_author(value)
        if value and not getattr(book, field):
            setattr(book, field, value[:255] if field != 'description' else value)

    # Язык нормализуем: в файлах пишут и «en», и «en-US», и «en_GB».
    language = (data.get('language') or '').strip().lower().replace('_', '-')
    if language and not book.language:
        book.language = language.split('-')[0][:10]

    if data.get('cover_bytes') and not book.cover:
        # save=False — файл кладём на диск, а запись в базу произойдёт ниже, одним махом.
        book.cover.save(data.get('cover_name', 'cover.jpg'), ContentFile(data['cover_bytes']), save=False)


def relink_progress(book: Book, positions: dict) -> int:
    """Возвращает записям прогресса ссылку на главу по её порядковому номеру."""
    if not positions:
        return 0

    chapters = {chapter.order: chapter for chapter in book.chapters.all()}
    restored = []

    for progress in book.progress_entries.filter(pk__in=positions):
        chapter = chapters.get(positions[progress.pk])
        if chapter is not None:
            progress.chapter = chapter
            restored.append(progress)

    if restored:
        ReadingProgress.objects.bulk_update(restored, ['chapter'])
    return len(restored)


def restore_progress_from_percent(book: Book) -> int:
    """Чинит записи, у которых ссылка на главу уже потеряна.

    Номер главы восстанавливаем из процента прочитанного: он считался
    по объёму текста, значит по нему же можно найти нужную главу обратно.
    """
    chapters = list(book.chapters.order_by('order'))
    total = sum(chapter.char_count for chapter in chapters)
    if not chapters or not total:
        return 0

    broken = list(book.progress_entries.filter(chapter__isnull=True))
    fixed = []

    for progress in broken:
        target = max(0.0, min(1.0, progress.percent / 100)) * total
        passed = 0
        for chapter in chapters:
            if passed + chapter.char_count >= target or chapter is chapters[-1]:
                progress.chapter = chapter
                size = chapter.char_count or 1
                progress.scroll_ratio = max(0.0, min(1.0, (target - passed) / size))
                fixed.append(progress)
                break
            passed += chapter.char_count

    if fixed:
        ReadingProgress.objects.bulk_update(fixed, ['chapter', 'scroll_ratio'])
    return len(fixed)


# Некоторые источники пишут в поле автора служебное слово:
# Викитека отдаёт «автор Александр Сергеевич Пушкин».
AUTHOR_PREFIX = re.compile(r'^\s*(автор|author|by)\b[\s:.-]*', re.I)


def _clean_author(value: str) -> str:
    """Убирает служебную приставку перед именем автора."""
    return AUTHOR_PREFIX.sub('', value or '').strip()
