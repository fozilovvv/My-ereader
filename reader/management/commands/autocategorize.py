"""Расставляет жанры уже загруженным книгам по метаданным их файлов.

    python manage.py autocategorize                  показать, что получится
    python manage.py autocategorize --apply          записать
    python manage.py autocategorize --apply --force  перезаписать существующие

Главы не пересобираются, поэтому цитаты и прогресс чтения не страдают.

Сама привязка делается общей функцией parsing.apply_categories — той же,
что работает при импорте книги. Раньше команда повторяла её логику своими
словами и однажды разошлась с ней: match() стала возвращать коды жанров,
а команда всё ещё сравнивала результат с названиями.
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from reader.models import Book
from reader.parsing import METADATA_READERS, apply_categories


class Command(BaseCommand):
    help = 'Проставляет жанры книгам по метаданным их файлов'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Записать изменения')
        parser.add_argument('--force', action='store_true',
                            help='Заменить уже проставленные жанры')

    def handle(self, *args, **options):
        changed = 0

        for book in Book.objects.all():
            current = sorted(category.name for category in book.categories.all())
            if current and not options['force']:
                continue
            if not book.source_file:
                continue

            subjects = self._subjects(book)

            # Считаем предполагаемый результат, ничего не записывая: для этого
            # временно очищаем связи только в режиме записи.
            if options['apply']:
                book.categories.clear()
                names = apply_categories(book, subjects)
            else:
                names = self._preview(book, subjects)

            if not names:
                if options['apply'] and current:
                    # Ничего не распознали — возвращаем как было.
                    book.categories.set(
                        book.categories.model.objects.filter(name__in=current)
                    )
                hint = ', '.join(subjects[:3]) or 'их нет ни в файле, ни в каталоге'
                self.stdout.write(f'  – {book.title[:40]} — жанры не распознаны ({hint})')
                continue

            if sorted(names) == current:
                continue

            self.stdout.write(f'  + {book.title[:40]:42} {current or "—"} -> {sorted(names)}')
            changed += 1

        self.stdout.write('')
        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                f'Черновой прогон. Книг к обновлению: {changed}. Повтори с --apply.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'Обновлено книг: {changed}.'))

    @staticmethod
    def _subjects(book) -> list:
        """Жанры из файла книги. Пусто — не беда, apply_categories спросит каталог."""
        reader = METADATA_READERS.get(Path(book.source_file.name).suffix.lower())
        if reader is None:
            return []
        try:
            with book.source_file.open('rb') as handle:
                return (reader(handle.read()) or {}).get('subjects', [])
        except Exception:
            return []

    @staticmethod
    def _preview(book, subjects) -> list:
        """Что получилось бы, не записывая ничего в базу."""
        from reader import categorizing
        from reader.models import Category
        from reader.parsing import catalog_subjects

        if not subjects:
            subjects = catalog_subjects(book)

        codes = categorizing.match(subjects)
        if not codes:
            return []

        language = (book.language or '').lower()[:2]
        if language != Category.Language.RU:
            language = Category.Language.EN

        return [
            category.name
            for category in Category.objects.filter(code__in=codes, language=language)
        ]
