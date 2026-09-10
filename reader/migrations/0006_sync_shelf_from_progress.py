"""Миграция данных: приводим полки в соответствие с прогрессом чтения.

Модель Shelf появилась позже ReadingProgress, поэтому у старых записей
прогресса полки не было вовсе. Плюс книга могла остаться в статусе
«В планах», хотя её уже читают.

Миграции меняют не только структуру таблиц, но и содержимое — это
правильное место для разовых починок данных: они выполнятся ровно один
раз и на любой машине, куда попадёт проект.
"""
from django.db import migrations

READING = 'reading'
FINISHED = 'finished'
PLANNED = 'planned'

# Порог «книга дочитана» — тот же, что в reader/views.py
FINISHED_PERCENT = 99


def sync_shelf(apps, schema_editor):
    ReadingProgress = apps.get_model('reader', 'ReadingProgress')
    Shelf = apps.get_model('reader', 'Shelf')

    shelves = {
        (entry.user_id, entry.book_id): entry
        for entry in Shelf.objects.all()
    }

    created, updated = [], []

    for progress in ReadingProgress.objects.all():
        if progress.percent <= 0:
            continue

        status = FINISHED if progress.percent >= FINISHED_PERCENT else READING
        shelf = shelves.get((progress.user_id, progress.book_id))

        if shelf is None:
            created.append(Shelf(
                user_id=progress.user_id,
                book_id=progress.book_id,
                status=status,
            ))
        elif shelf.status in ('', PLANNED):
            # Осознанный выбор «Читаю» или «Прочитано» не трогаем —
            # заменяем только пустое значение и устаревшее «В планах».
            shelf.status = status
            updated.append(shelf)

    if created:
        Shelf.objects.bulk_create(created)
    if updated:
        Shelf.objects.bulk_update(updated, ['status'])


def noop(apps, schema_editor):
    """Откат не нужен: миграция только добивает недостающие данные."""


class Migration(migrations.Migration):

    dependencies = [
        ('reader', '0005_book_search_text'),
    ]

    operations = [
        migrations.RunPython(sync_shelf, noop),
    ]
