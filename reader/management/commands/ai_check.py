"""Проверка связи с Claude API.

Свои команды Django ищет в папке management/commands/ любого приложения.
Имя файла = имя команды: python manage.py ai_check
"""
from django.core.management.base import BaseCommand

from reader import ai


class Command(BaseCommand):
    help = 'Проверяет, что ключ ANTHROPIC_API_KEY рабочий'

    def handle(self, *args, **options):
        from django.conf import settings

        if settings.AI_MOCK:
            self.stdout.write(self.style.WARNING('Режим: ЗАГЛУШКА (ключ не задан)'))
        else:
            self.stdout.write(f'Режим: реальный запрос, модель {ai.MODEL}')

        try:
            answer = ai.ask(
                'translate',
                fragment='ветхий',
                context='Он поднялся по ветхой лестнице на второй этаж.',
            )
        except ai.AiError as error:
            self.stderr.write(self.style.ERROR(f'Не получилось: {error}'))
            return

        label = 'Заглушка вернула:' if settings.AI_MOCK else 'Связь есть. Ответ модели:'
        self.stdout.write(self.style.SUCCESS(label))
        self.stdout.write(answer)
