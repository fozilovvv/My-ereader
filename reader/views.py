"""Представления (views): принимают запрос — отдают готовую страницу."""
import json
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from pathlib import Path
from urllib.parse import quote_plus

from django.core.files.base import ContentFile

from . import ai, fetching, search, sources
from .forms import BookRequestForm, BookUploadForm, BookUrlForm, SignUpForm
from .models import (Book, BookRequest, CatalogEntry, Category, Chapter, Quote,
                     ReadingProgress, Shelf)
from .parsing import PARSERS, ParseError, import_book
from .templatetags.library_extras import cover_hue, reading_time


def _progress_map(user) -> dict:
    """Весь прогресс пользователя одним запросом: id книги → запись прогресса."""
    if not user.is_authenticated:
        return {}
    entries = ReadingProgress.objects.select_related('chapter', 'book').filter(user=user)
    return {entry.book_id: entry for entry in entries}


def _shelf_map(user) -> dict:
    """Вся полка пользователя одним запросом: id книги → запись полки."""
    if not user.is_authenticated:
        return {}
    return {entry.book_id: entry for entry in Shelf.objects.filter(user=user)}


def book_list(request):
    """Каталог с поиском и фильтрами по категории и полке."""
    query = request.GET.get('q', '').strip()
    category_slug = request.GET.get('category', '').strip()
    shelf_filter = request.GET.get('shelf', '').strip()
    sort = request.GET.get('sort', 'new').strip()

    books = (
        Book.objects
        .filter(status=Book.Status.READY)
        .prefetch_related('categories')                       # чтобы не дёргать базу на каждую книгу
        .annotate(chapters_total=Count('chapters', distinct=True))
    )
    # Каждое слово запроса должно найтись в книге — так «тихой хранитель»
    # находит «Хранитель тихой станции», а порядок слов не важен.
    for term in search.terms(query):
        books = books.filter(search_text__contains=term)
    if category_slug:
        books = books.filter(categories__slug=category_slug)

    # Белый список сортировок: в order_by нельзя пускать строку от пользователя.
    ORDERINGS = {
        'new': '-created_at',
        'title': 'title',
        'author': 'author',
        'long': '-total_chars',
        'short': 'total_chars',
    }
    books = books.order_by(ORDERINGS.get(sort, ORDERINGS['new']))

    books = list(books)
    progress = _progress_map(request.user)
    shelves = _shelf_map(request.user)
    for book in books:
        book.progress = progress.get(book.id)
        book.shelf_entry = shelves.get(book.id)

    # Фильтр по полке применяем в Python: данные уже в памяти,
    # лишний запрос к базе ради этого делать незачем.
    if shelf_filter == 'favorite':
        books = [book for book in books if book.shelf_entry and book.shelf_entry.is_favorite]
    elif shelf_filter in Shelf.Status.values:
        books = [book for book in books if book.shelf_entry and book.shelf_entry.status == shelf_filter]

    # Сортировка по прогрессу возможна только после загрузки данных о нём.
    if sort == 'progress':
        books.sort(key=lambda b: b.progress.percent if b.progress else -1, reverse=True)

    reading = sorted(
        (book for book in books if book.progress and 0 < book.progress.percent < 99.5),
        key=lambda book: book.progress.updated_at,
        reverse=True,
    )

    return render(request, 'reader/book_list.html', {
        'books': books,
        'query': query,
        'reading': [] if (query or category_slug or shelf_filter) else reading[:6],
        'category_groups': _category_groups(category_slug),
        'current_category': category_slug,
        'current_shelf': shelf_filter,
        'current_sort': sort,
        'shelf_counts': _shelf_counts(shelves),
        'stats': _reading_stats(request.user, progress, shelves),
        'total_books': len(books),
    })


def _reading_stats(user, progress: dict, shelves: dict):
    """Личная статистика для сайдбара. Считается по уже загруженным данным."""
    if not user.is_authenticated:
        return None

    # Сколько текста реально прочитано: объём книги на долю пройденного.
    chars = sum(
        (entry.book.total_chars or 0) * entry.percent / 100
        for entry in progress.values()
    )
    statuses = [entry.status for entry in shelves.values()]

    return {
        'finished': statuses.count(Shelf.Status.FINISHED),
        'reading': statuses.count(Shelf.Status.READING),
        'chars': int(chars),
    }


def _category_groups(current_slug: str = '') -> list:
    """Категории, разложенные по языкам: русские отдельно, английские отдельно.

    Пустые категории в сайдбар не показываем: список из 52 пунктов, половина
    которых ни к чему не ведёт, только мешает.

    Раздел с выбранной категорией помечаем open — иначе после клика по жанру
    список схлопнулся бы, и стало бы непонятно, где ты находишься. Пока
    ничего не выбрано, все разделы closed: сайдбар остаётся коротким,
    а списки открываются по клику.
    """
    used = (
        Category.objects
        .annotate(total=Count('books'))
        .filter(total__gt=0)
        .order_by('language', 'position', 'name')
    )

    groups = []
    for language, label in Category.Language.choices:
        items = [category for category in used if category.language == language]
        if items:
            groups.append({
                'label': label,
                'items': items,
                'open': any(category.slug == current_slug for category in items),
            })

    return groups


def _shelf_counts(shelves: dict) -> dict:
    """Счётчики для сайдбара. Считаем по уже загруженным данным, без запросов."""
    entries = shelves.values()
    return {
        'planned': sum(1 for e in entries if e.status == Shelf.Status.PLANNED),
        'reading': sum(1 for e in entries if e.status == Shelf.Status.READING),
        'finished': sum(1 for e in entries if e.status == Shelf.Status.FINISHED),
        'favorite': sum(1 for e in entries if e.is_favorite),
    }


def book_detail(request, slug):
    """Карточка книги: описание и оглавление."""
    book = get_object_or_404(Book, slug=slug)
    chapters = list(book.chapters.only('order', 'title', 'char_count', 'book'))

    return render(request, 'reader/book_detail.html', {
        'book': book,
        'chapters': chapters,
        'total_chars': sum(chapter.char_count for chapter in chapters),
        'progress': _progress_map(request.user).get(book.id),
        'shelf_entry': _shelf_map(request.user).get(book.id),
        'shelf_statuses': Shelf.Status.choices,
        'quotes_count': Quote.objects.filter(user=request.user, book=book).count()
                        if request.user.is_authenticated else 0,
    })


def chapter_read(request, slug, order):
    """Читалка: одна глава книги."""
    book = get_object_or_404(Book, slug=slug)
    chapter = get_object_or_404(Chapter, book=book, order=order)
    total = book.chapters.count()

    progress = _progress_map(request.user).get(book.id)
    # Прокрутку восстанавливаем, только если человек ушёл именно с этой главы.
    on_this_chapter = progress is not None and progress.chapter_id == chapter.id

    return render(request, 'reader/chapter_read.html', {
        'book': book,
        'chapter': chapter,
        'chapters': book.chapters.only('order', 'title', 'book'),
        'prev_order': order - 1 if order > 0 else None,
        'next_order': order + 1 if order + 1 < total else None,
        'position': order + 1,
        'total': total,
        'restore': progress.scroll_ratio if on_this_chapter else 0,
        'chapter_quotes': _chapter_quotes(request.user, chapter),
    })


def _staff_only(request, action='Этот раздел'):
    """Наполнение каталога и работа с заявками — дело администратора."""
    if not request.user.is_staff:
        raise PermissionDenied(f'{action} доступен только администратору.')


def _finish_import(request, book: Book, form, field: str):
    """Разбирает новую книгу. Возвращает redirect при успехе или None при ошибке."""
    try:
        created = import_book(book)
    except Exception as error:
        # Ловим широко: сбой парсера — проблема одной книги, а не повод
        # показать пользователю страницу с трассировкой.
        book.status = Book.Status.ERROR
        book.parse_error = str(error)
        book.save(update_fields=['status', 'parse_error'])
        form.add_error(field, f'Файл сохранён, но разобрать не вышло: {error}')
        return None

    messages.success(request, f'«{book.title}» готова к чтению — глав: {created}')
    return redirect(book.get_absolute_url())


@login_required
def book_upload(request):
    """Загрузка книги файлом."""
    _staff_only(request, 'Добавление книг')
    form = BookUploadForm()

    if request.method == 'POST':
        form = BookUploadForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save(commit=False)
            book.uploaded_by = request.user      # запоминаем, кто принёс книгу
            book.save()
            done = _finish_import(request, book, form, 'source_file')
            if done:
                return done

    return render(request, 'reader/book_upload.html', {'form': form, 'url_form': BookUrlForm()})


@login_required
def book_import_url(request):
    """Импорт книги по прямой ссылке на файл."""
    _staff_only(request, 'Добавление книг')
    url_form = BookUrlForm(request.POST or None)

    if request.method == 'POST' and url_form.is_valid():
        try:
            data, filename = fetching.fetch(url_form.cleaned_data['url'])
        except fetching.FetchError as error:
            url_form.add_error('url', str(error))
        else:
            suffix = Path(filename).suffix.lower()
            if suffix not in PARSERS:
                supported = ', '.join(sorted(PARSERS))
                url_form.add_error('url', f'По ссылке файл «{suffix or "без расширения"}». Нужен один из: {supported}')
            else:
                book = Book(
                    uploaded_by=request.user,
                    title=url_form.cleaned_data['title'],
                    author=url_form.cleaned_data['author'],
                )
                # save=False: кладём файл на диск, запись в базу — следующей строкой
                book.source_file.save(filename, ContentFile(data), save=False)
                book.save()
                done = _finish_import(request, book, url_form, 'url')
                if done:
                    return done

    return render(request, 'reader/book_upload.html', {
        'form': BookUploadForm(), 'url_form': url_form,
    })


def search_api(request):
    """API для палитры Ctrl+K: мгновенный поиск по каталогу.

    Отдаёт готовые к показу данные — ссылку, оттенок обложки, время чтения,
    чтобы фронтенду не пришлось ничего досчитывать.
    """
    words = search.terms(request.GET.get('q', ''))
    if not words:
        return JsonResponse({'books': []})

    books = Book.objects.filter(status=Book.Status.READY)
    for word in words:
        books = books.filter(search_text__contains=word)

    return JsonResponse({'books': [
        {
            'title': book.title,
            'author': book.author or 'Автор не указан',
            'url': book.get_absolute_url(),
            'cover': book.cover.url if book.cover else '',
            'hue': cover_hue(book.title),
            'letter': (book.title[:1] or '?').upper(),
            'time': reading_time(book.total_chars),
        }
        for book in books[:8]
    ]})


def _chapter_quotes(user, chapter: Chapter) -> list:
    """Цитаты пользователя в этой главе — для подсветки прямо в тексте."""
    if not user.is_authenticated:
        return []
    return list(
        Quote.objects.filter(user=user, chapter=chapter).values('id', 'text', 'note')
    )


MAX_QUOTE_LENGTH = 2000
MAX_NOTE_LENGTH = 1000


@require_POST
def quote_create(request):
    """API: сохраняет выделенный фрагмент как цитату."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Требуется вход'}, status=401)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    chapter = Chapter.objects.filter(
        book__slug=payload.get('slug', ''), order=payload.get('order'),
    ).select_related('book').first()
    if chapter is None:
        return JsonResponse({'error': 'Глава не найдена'}, status=404)

    text = str(payload.get('text', '')).strip()[:MAX_QUOTE_LENGTH]
    if not text:
        return JsonResponse({'error': 'Пустая цитата'}, status=400)

    try:
        ratio = min(1.0, max(0.0, float(payload.get('scroll_ratio', 0))))
    except (TypeError, ValueError):
        ratio = 0.0

    quote = Quote.objects.create(
        user=request.user,
        book=chapter.book,
        chapter=chapter,
        text=text,
        note=str(payload.get('note', '')).strip()[:MAX_NOTE_LENGTH],
        scroll_ratio=ratio,
    )
    return JsonResponse({'id': quote.pk, 'text': quote.text})


@require_POST
def quote_update(request, pk):
    """API: правит заметку или удаляет цитату."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Требуется вход'}, status=401)

    # Фильтр по user обязателен: иначе по чужому id можно было бы
    # отредактировать или удалить цитату другого человека.
    quote = Quote.objects.filter(pk=pk, user=request.user).first()
    if quote is None:
        return JsonResponse({'error': 'Цитата не найдена'}, status=404)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    if payload.get('delete'):
        quote.delete()
        return JsonResponse({'deleted': True})

    quote.note = str(payload.get('note', '')).strip()[:MAX_NOTE_LENGTH]
    quote.save(update_fields=['note'])
    return JsonResponse({'id': quote.pk, 'note': quote.note})


@login_required
def quotes_list(request):
    """Страница «Мои цитаты»: всё сохранённое, сгруппированное по книгам."""
    quotes = (
        Quote.objects
        .filter(user=request.user)
        .select_related('book', 'chapter')
        .order_by('book__title', 'chapter__order', 'created_at')
    )

    book_slug = request.GET.get('book', '').strip()
    if book_slug:
        quotes = quotes.filter(book__slug=book_slug)

    # Группируем в Python: данные уже загружены, лишний запрос ни к чему.
    groups = {}
    for quote in quotes:
        groups.setdefault(quote.book, []).append(quote)

    return render(request, 'reader/quotes.html', {
        'groups': list(groups.items()),
        'total': len(quotes),
        'books': Book.objects.filter(quotes__user=request.user).distinct(),
        'current_book': book_slug,
    })


def book_request(request):
    """Заказ книги: читатель просит добавить то, чего в библиотеке нет."""
    if request.method == 'POST':
        form = BookRequestForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            # Гостям тоже разрешаем заказывать, поэтому user может остаться пустым.
            if request.user.is_authenticated:
                order.user = request.user
            order.save()
            messages.success(request, 'Заказ принят — посмотрим, что можно найти.')
            return redirect('reader:book_list')
    else:
        form = BookRequestForm()

    return render(request, 'reader/book_request.html', {
        'form': form,
        'my_requests': (
            BookRequest.objects.filter(user=request.user)[:10]
            if request.user.is_authenticated else []
        ),
    })


@login_required
def book_request_list(request):
    """Заказы читателей — страница для администратора прямо на сайте.

    В админку Django ходить не обязательно: смотреть заявки и менять их
    статус удобнее там же, где живёт остальная библиотека.
    """
    _staff_only(request, 'Раздел заказов')

    # Смена статуса — обычная форма без JavaScript: одна кнопка, один POST.
    if request.method == 'POST':
        order = BookRequest.objects.filter(pk=request.POST.get('pk')).first()
        status = request.POST.get('status', '')
        if order is None:
            messages.error(request, 'Заказ не найден.')
        elif status not in BookRequest.Status.values:
            messages.error(request, 'Неизвестный статус.')
        else:
            order.status = status
            order.save(update_fields=['status'])
            messages.success(request, f'«{order}» — {order.get_status_display().lower()}')
        return redirect(f"{request.path}?{request.GET.urlencode()}")

    current = request.GET.get('status', '').strip()
    orders = BookRequest.objects.select_related('user')
    if current in BookRequest.Status.values:
        orders = orders.filter(status=current)

    # Счётчики считаем по всем заказам, а не по отфильтрованным: иначе
    # вкладки показывали бы ноль у всех, кроме выбранной. Склеиваем их со
    # статусами прямо здесь — в шаблоне Django нельзя взять значение
    # словаря по переменному ключу.
    counts = {value: 0 for value, _ in BookRequest.Status.choices}
    for status in BookRequest.objects.values_list('status', flat=True):
        counts[status] = counts.get(status, 0) + 1

    tabs = [
        {'value': value, 'label': label, 'count': counts.get(value, 0)}
        for value, label in BookRequest.Status.choices
    ]

    return render(request, 'reader/book_requests.html', {
        'orders': orders,
        'statuses': BookRequest.Status.choices,
        'tabs': tabs,
        'current_status': current,
        'total': sum(counts.values()),
    })


@login_required
def catalog_find(request):
    """Поиск книги во внешних источниках и добавление её в библиотеку."""
    _staff_only(request, 'Поиск по каталогу')

    if request.method == 'POST':
        return _import_from_source(request)

    source = request.GET.get('source', sources.GUTENBERG).strip()
    if source not in {item['code'] for item in sources.SOURCES}:
        source = sources.GUTENBERG

    mode = request.GET.get('mode', 'works').strip()
    if mode not in ('works', 'authors'):
        mode = 'works'

    query = request.GET.get('q', '').strip()
    language = request.GET.get('lang', '').strip()
    author_page = request.GET.get('author', '').strip()
    order_pk = request.GET.get('order', '').strip()

    results, error, author_name = [], '', ''

    try:
        if author_page:
            # Открыт список произведений конкретного писателя.
            author_name = author_page.removeprefix(sources.AUTHOR_PREFIX)
            results = sources.author_works(author_page, query)
        elif query:
            results = sources.find(source, query, language, mode)
    except sources.SourceError as problem:
        error = str(problem)

    return render(request, 'reader/catalog_find.html', {
        'query': query,
        'language': language,
        'source': source,
        'mode': mode,
        'sources': sources.SOURCES,
        'results': sources.mark_existing(results),
        'error': error,
        'author_page': author_page,
        'author_name': author_name,
        'popular_authors': sources.POPULAR_AUTHORS,
        'languages': sources.languages_in_catalog(),
        'catalog_size': CatalogEntry.objects.count(),
        'order': BookRequest.objects.filter(pk=order_pk).first() if order_pk else None,
    })


def _import_from_source(request):
    """Скачивает выбранную книгу из источника и заводит её в библиотеке."""
    source = request.POST.get('source', sources.GUTENBERG)
    key = request.POST.get('key', '').strip()
    if not key:
        messages.error(request, 'Книга не выбрана.')
        return redirect('reader:catalog_find')

    back = (f"{reverse('reader:catalog_find')}?source={quote_plus(source)}"
            f"&q={quote_plus(request.POST.get('q', ''))}")

    try:
        data, filename = fetching.fetch(sources.download_url(source, key))
    except fetching.FetchError as error:
        messages.error(request, f'Не удалось скачать: {error}')
        return redirect(back)

    # Викитека отдаёт файл без говорящего имени — собираем его из названия.
    if not filename.lower().endswith('.epub'):
        safe = slugify(request.POST.get('title', key), allow_unicode=True)[:80]
        filename = f'{safe or "book"}.epub'

    book = Book(uploaded_by=request.user)
    # Название и автора не задаём: их аккуратнее прочитает парсер из файла.
    book.source_file.save(filename, ContentFile(data), save=False)
    book.save()

    try:
        created = import_book(book)
    except Exception as error:
        book.delete()
        messages.error(request, f'Файл скачался, но разобрать не вышло: {error}')
        return redirect(back)

    # Викитека не хранит жанров: это архив классики в общественном
    # достоянии, поэтому осмысленный запасной вариант тут есть.
    if source == sources.WIKISOURCE and not book.categories.exists():
        fallback = Category.objects.filter(
            code='classics', language=Category.Language.RU,
        ).first()
        if fallback:
            book.categories.add(fallback)

    # Если книгу искали по заявке — закрываем её.
    order = BookRequest.objects.filter(pk=request.POST.get('order')).first()
    if order is not None:
        order.status = BookRequest.Status.DONE
        order.save(update_fields=['status'])

    messages.success(request, f'«{book.title}» добавлена — глав: {created}')
    return redirect(book.get_absolute_url())


def signup(request):
    """Регистрация: создаём пользователя и сразу входим под ним."""
    if request.user.is_authenticated:
        return redirect('reader:book_list')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('reader:book_list')
    else:
        form = SignUpForm()

    return render(request, 'registration/signup.html', {'form': form})


@require_POST
def save_progress(request):
    """API: сохраняет позицию чтения. Отвечает JSON, а не HTML-страницей."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Требуется вход'}, status=401)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    book = Book.objects.filter(slug=payload.get('slug', '')).first()
    if book is None:
        return JsonResponse({'error': 'Книга не найдена'}, status=404)

    chapter = book.chapters.filter(order=payload.get('order')).first()
    if chapter is None:
        return JsonResponse({'error': 'Глава не найдена'}, status=404)

    # Никогда не доверяем числу из браузера: зажимаем его в диапазон 0..1.
    try:
        ratio = min(1.0, max(0.0, float(payload.get('scroll_ratio', 0))))
    except (TypeError, ValueError):
        ratio = 0.0

    percent = _book_percent(book, chapter, ratio)

    ReadingProgress.objects.update_or_create(
        user=request.user,
        book=book,
        defaults={'chapter': chapter, 'scroll_ratio': ratio, 'percent': percent},
    )
    _sync_shelf(request.user, book, percent)

    return JsonResponse({'ok': True, 'percent': percent})


def _sync_shelf(user, book: Book, percent: float) -> None:
    """Статус книги — прямая функция от прогресса чтения.

    Дочитал до конца — «Прочитано». Читает дальше или начал заново —
    «Читаю сейчас». Раньше здесь стояло правило «не перебивать выбор
    пользователя», из-за него перечитываемая книга навсегда застревала
    в «Прочитано». Простое правило оказалось и честнее, и предсказуемее:
    статус всегда описывает то, что происходит на самом деле.

    «В планах» это не ломает: у непрочитанной книги прогресса нет,
    и эта функция для неё просто не вызывается.
    """
    shelf, _ = Shelf.objects.get_or_create(user=user, book=book)

    new_status = (
        Shelf.Status.FINISHED if percent >= Shelf.FINISHED_PERCENT
        else Shelf.Status.READING
    )

    if new_status != shelf.status:
        shelf.status = new_status
        shelf.save(update_fields=['status', 'updated_at'])


@require_POST
def shelf_update(request):
    """API: меняет статус книги и флаг избранного."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Требуется вход'}, status=401)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    book = Book.objects.filter(slug=payload.get('slug', '')).first()
    if book is None:
        return JsonResponse({'error': 'Книга не найдена'}, status=404)

    shelf, _ = Shelf.objects.get_or_create(user=request.user, book=book)

    if 'status' in payload:
        status = str(payload['status'] or '')
        if status and status not in Shelf.Status.values:
            return JsonResponse({'error': 'Неизвестный статус'}, status=400)
        # Повторное нажатие той же кнопки снимает статус — привычное поведение.
        shelf.status = '' if shelf.status == status else status

    if 'favorite' in payload:
        shelf.is_favorite = bool(payload['favorite'])

    # Пустая запись полке не нужна — не копим мусор в базе.
    if not shelf.status and not shelf.is_favorite:
        shelf.delete()
        return JsonResponse({'status': '', 'favorite': False})

    shelf.save()
    return JsonResponse({'status': shelf.status, 'favorite': shelf.is_favorite})


def _book_percent(book: Book, chapter: Chapter, ratio: float) -> float:
    """Процент книги считаем по символам, а не по номеру главы.

    Иначе короткий пролог давал бы такой же вклад, как глава на сорок страниц.
    """
    sizes = dict(book.chapters.values_list('order', 'char_count'))
    total = sum(sizes.values()) or 1
    before = sum(size for order, size in sizes.items() if order < chapter.order)
    return round((before + ratio * chapter.char_count) / total * 100, 1)


# --- AI: перевод, объяснение, выжимка --------------------------------------

MAX_FRAGMENT = 2000     # символов в выделенном фрагменте
MAX_CONTEXT = 4000      # символов окружающего текста


@require_POST
def ai_assist(request):
    """API: отправляет фрагмент книги в Claude и возвращает ответ."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Войди, чтобы пользоваться AI-помощником'}, status=401)

    if _rate_limited(request.user):
        return JsonResponse(
            {'error': 'Слишком часто. Подожди минуту.'}, status=429)

    try:
        payload = json.loads(request.body or b'{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Некорректный JSON'}, status=400)

    action = payload.get('action', '')
    if action not in ai.ACTIONS:
        return JsonResponse({'error': 'Неизвестное действие'}, status=400)

    if action == 'summarize':
        # Текст главы берём из базы, а не из браузера: так его нельзя подменить
        # на что-то огромное и дорогое, и не нужно гонять по сети лишние килобайты.
        chapter = Chapter.objects.filter(
            book__slug=payload.get('slug', ''), order=payload.get('order'),
        ).first()
        if chapter is None:
            return JsonResponse({'error': 'Глава не найдена'}, status=404)
        fragment, context = _chapter_text(chapter)[:MAX_CONTEXT * 2], ''
    else:
        fragment = str(payload.get('fragment', '')).strip()[:MAX_FRAGMENT]
        context = str(payload.get('context', '')).strip()[:MAX_CONTEXT]
        if not fragment:
            return JsonResponse({'error': 'Пустой фрагмент'}, status=400)

    try:
        answer = ai.ask(action, fragment, context)
    except ai.AiError as error:
        return JsonResponse({'error': str(error)}, status=502)

    return JsonResponse({'answer': answer, 'demo': settings.AI_MOCK})


def _chapter_text(chapter: Chapter) -> str:
    """HTML главы в чистый текст.

    Перед вырезанием тегов ставим перенос строки на месте закрывающих блочных
    тегов — иначе strip_tags склеит заголовок с первым абзацем в одно слово.
    """
    text = re.sub(r'</(p|div|h[1-6]|li|blockquote)>', '\n', chapter.content, flags=re.I)
    return strip_tags(text).strip()


def _rate_limited(user) -> bool:
    """Простой счётчик запросов в минуту: обращения к модели стоят денег."""
    key = f'ai-rate:{user.pk}'
    used = cache.get(key, 0)
    if used >= settings.AI_RATE_LIMIT_PER_MINUTE:
        return True
    cache.set(key, used + 1, timeout=60)
    return False
