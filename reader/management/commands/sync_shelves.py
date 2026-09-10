"""Пересчитывает статусы полок по прогрессу чтения.

Нужна, если статусы разошлись с реальностью: после смены правил,
переноса данных или ручной правки в админке.

    python manage.py sync_shelves          показать, что изменится
    python manage.py sync_shelves --apply  применить
"""
from django.core.management.base import BaseCommand

from reader.models import ReadingProgress, Shelf


class Command(BaseCommand):
    help = 'Приводит статусы полок в соответствие с прогрессом чтения'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply', action='store_true',
            help='Записать изменения (без флага только показывает)',
        )

    def handle(self, *args, **options):
        apply_changes = options['apply']

        shelves = {
            (entry.user_id, entry.book_id): entry
            for entry in Shelf.objects.all()
        }
        created, updated = [], []

        for progress in ReadingProgress.objects.select_related('book', 'user'):
            if progress.percent <= 0:
                continue

            status = (
                Shelf.Status.FINISHED if progress.percent >= Shelf.FINISHED_PERCENT
                else Shelf.Status.READING
            )
            shelf = shelves.get((progress.user_id, progress.book_id))

            if shelf is None:
                created.append(Shelf(user_id=progress.user_id, book_id=progress.book_id, status=status))
                self.stdout.write(f'  + {progress.user} · {progress.book} -> {status}')
            elif shelf.status != status:
                self.stdout.write(f'  ~ {progress.user} · {progress.book}: {shelf.status or "пусто"} -> {status}')
                shelf.status = status
                updated.append(shelf)

        if not created and not updated:
            self.stdout.write(self.style.SUCCESS('Всё уже согласовано, менять нечего.'))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                f'Черновой прогон. Создать: {len(created)}, изменить: {len(updated)}. '
                'Повтори с флагом --apply, чтобы записать.'
            ))
            return

        if created:
            Shelf.objects.bulk_create(created)
        if updated:
            Shelf.objects.bulk_update(updated, ['status'])
        self.stdout.write(self.style.SUCCESS(
            f'Готово. Создано: {len(created)}, обновлено: {len(updated)}.'
        ))
