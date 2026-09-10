"""Наполняет справочник жанров: python manage.py seed_categories

Создаёт каждый жанр в двух вариантах — русском и английском. Повторный
запуск безопасен: существующие записи обновляются, дубли не плодятся.
"""
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from reader.genres import names_by_language
from reader.models import Category


class Command(BaseCommand):
    help = 'Заполняет справочник жанров русскими и английскими названиями'

    def handle(self, *args, **options):
        created = updated = 0

        for code, language, name, position in names_by_language():
            # Ключ — пара «код + язык»: именно она уникальна в модели.
            category, is_new = Category.objects.update_or_create(
                code=code,
                language=language,
                defaults={
                    'name': name,
                    'position': position,
                    'slug': slugify(f'{name}-{language}', allow_unicode=True),
                },
            )
            created += is_new
            updated += not is_new

        self.stdout.write(self.style.SUCCESS(
            f'Создано: {created}, обновлено: {updated}. '
            f'Всего в справочнике: {Category.objects.count()}'
        ))
