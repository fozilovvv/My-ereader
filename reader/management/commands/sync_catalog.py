"""Скачивает каталог Project Gutenberg и сохраняет его в базу.

    python manage.py sync_catalog

Каталог — один CSV-файл примерно на 20 МБ, около 79 тысяч книг. Качаем
его целиком и раскладываем по таблице, чтобы поиск шёл локально: публичный
поиск Gutendex отвечает около ста секунд, что для формы неприемлемо.

Команду достаточно запускать изредка — каталог пополняется медленно.
"""
import csv
import io
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

from reader import search
from reader.models import CatalogEntry

CATALOG_URL = 'https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv'
USER_AGENT = 'PersonalLibrary/1.0 (+book import)'
TIMEOUT = 180          # файл большой, качается около минуты
BATCH = 2000


class Command(BaseCommand):
    help = 'Загружает каталог Project Gutenberg для поиска книг'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Взять только N первых записей (для проверки)')

    def handle(self, *args, **options):
        self.stdout.write(f'Скачиваю каталог: {CATALOG_URL}')
        try:
            request = Request(CATALOG_URL, headers={'User-Agent': USER_AGENT})
            with urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
        except (URLError, TimeoutError) as error:
            self.stderr.write(self.style.ERROR(f'Не удалось скачать: {error}'))
            return

        self.stdout.write(f'Получено {len(raw) // 1024 // 1024} МБ, разбираю…')

        rows = csv.DictReader(io.StringIO(raw.decode('utf-8')))
        entries = []
        skipped = 0

        for row in rows:
            # В каталоге есть не только книги: там же записи звука и данных.
            if (row.get('Type') or '').strip() != 'Text':
                skipped += 1
                continue

            try:
                number = int(row['Text#'])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue

            title = ' '.join((row.get('Title') or '').split())[:500]
            authors = ' '.join((row.get('Authors') or '').split())[:500]
            if not title:
                skipped += 1
                continue

            entries.append(CatalogEntry(
                gutenberg_id=number,
                title=title,
                authors=authors,
                language=(row.get('Language') or '').strip()[:20],
                subjects=(row.get('Subjects') or '').strip(),
                search_text=search.normalize(f'{title} {authors}')[:1000],
            ))

            if options['limit'] and len(entries) >= options['limit']:
                break

        # Полная замена: каталог приходит целиком, поэтому проще заменить
        # его целиком, чем сверять каждую строку по отдельности.
        CatalogEntry.objects.all().delete()
        for start in range(0, len(entries), BATCH):
            CatalogEntry.objects.bulk_create(entries[start:start + BATCH])

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Книг в каталоге: {len(entries)}, пропущено записей: {skipped}.'
        ))
