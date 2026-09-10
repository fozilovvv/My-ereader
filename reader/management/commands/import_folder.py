r"""Массовый импорт книг из папки.

    python manage.py import_folder C:\Books            показать, что будет
    python manage.py import_folder C:\Books --apply    загрузить
    python manage.py import_folder C:\Books --apply -r  вместе с подпапками
"""
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from reader.models import Book
from reader.parsing import PARSERS, import_book

MAX_MB = 50


class Command(BaseCommand):
    help = 'Загружает в библиотеку все книги из указанной папки'

    def add_arguments(self, parser):
        parser.add_argument('folder', help='Папка с файлами книг')
        parser.add_argument('--apply', action='store_true', help='Записать (без флага — черновой прогон)')
        parser.add_argument('-r', '--recursive', action='store_true', help='Заходить в подпапки')

    def handle(self, *args, **options):
        folder = Path(options['folder'])
        if not folder.is_dir():
            raise CommandError(f'Папка не найдена: {folder}')

        pattern = '**/*' if options['recursive'] else '*'
        files = sorted(
            path for path in folder.glob(pattern)
            if path.is_file() and path.suffix.lower() in PARSERS
        )
        if not files:
            supported = ', '.join(sorted(PARSERS))
            self.stdout.write(self.style.WARNING(f'Книг не найдено. Ищу файлы: {supported}'))
            return

        # Уже загруженные узнаём по имени файла — так повторный запуск
        # не создаёт дублей и его можно спокойно повторять.
        known = {
            Path(name).name.lower()
            for name in Book.objects.values_list('source_file', flat=True)
        }

        imported = skipped = failed = 0

        for path in files:
            if path.name.lower() in known:
                self.stdout.write(f'  = {path.name} — уже в библиотеке')
                skipped += 1
                continue

            size_mb = path.stat().st_size / 1024 / 1024
            if size_mb > MAX_MB:
                self.stdout.write(self.style.WARNING(f'  ! {path.name} — {size_mb:.1f} МБ, пропускаю'))
                skipped += 1
                continue

            if not options['apply']:
                self.stdout.write(f'  + {path.name} ({size_mb:.1f} МБ)')
                imported += 1
                continue

            book = Book()
            book.source_file.save(path.name, ContentFile(path.read_bytes()), save=False)
            book.save()

            try:
                chapters = import_book(book)
            except Exception as error:
                book.status = Book.Status.ERROR
                book.parse_error = str(error)
                book.save(update_fields=['status', 'parse_error'])
                self.stdout.write(self.style.ERROR(f'  x {path.name} — {error}'))
                failed += 1
            else:
                self.stdout.write(self.style.SUCCESS(f'  + {book.title} — глав: {chapters}'))
                imported += 1

        self.stdout.write('')
        if not options['apply']:
            self.stdout.write(self.style.WARNING(
                f'Черновой прогон. Готово к загрузке: {imported}, пропущено: {skipped}. '
                'Повтори с флагом --apply.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Загружено: {imported}, пропущено: {skipped}, с ошибкой: {failed}.'
            ))
