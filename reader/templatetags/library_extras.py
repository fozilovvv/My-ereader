"""Свои фильтры и теги для шаблонов библиотеки.

Шаблоны Django намеренно не умеют вычислять — вся логика живёт в Python.
Такие мелкие вычисления оформляются фильтрами: они переиспользуются
на любой странице и тестируются как обычные функции.
"""
import zlib

from django import template

register = template.Library()

# Средняя скорость чтения прозы — около 1300 символов в минуту.
CHARS_PER_MINUTE = 1300


@register.filter
def cover_hue(text: str) -> int:
    """Стабильный оттенок (0–359) из названия книги.

    crc32 — быстрая контрольная сумма: одно и то же название всегда даёт
    один и тот же цвет, поэтому обложка книги не «мигает» между заходами.
    """
    if not text:
        return 30
    return zlib.crc32(str(text).encode('utf-8')) % 360


def _humanize(minutes: int) -> str:
    if minutes < 1:
        return 'меньше минуты'
    if minutes < 60:
        return f'{minutes} мин'
    hours, rest = divmod(minutes, 60)
    return f'{hours} ч' if rest == 0 else f'{hours} ч {rest} мин'


@register.filter
def reading_time(chars) -> str:
    """Сколько читать книгу целиком: «≈ 2 ч 15 мин»."""
    try:
        minutes = round(int(chars) / CHARS_PER_MINUTE)
    except (TypeError, ValueError):
        return ''
    return _humanize(minutes)


@register.filter
def time_left(book) -> str:
    """Сколько осталось читать с учётом прогресса."""
    total = getattr(book, 'total_chars', 0) or 0
    if not total:
        return ''

    progress = getattr(book, 'progress', None)
    done = (progress.percent / 100) if progress else 0
    remaining = round(total * max(0.0, 1 - done) / CHARS_PER_MINUTE)

    if progress and done > 0:
        return f'осталось ~{_humanize(remaining)}'
    return f'~{_humanize(remaining)}'


@register.simple_tag(takes_context=True)
def query_replace(context, **kwargs) -> str:
    """Меняет один параметр в адресе, сохраняя остальные.

    Без него ссылка на категорию сбрасывала бы поиск и сортировку.
    Пустое значение убирает параметр совсем.
    """
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        if value in ('', None):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f'?{encoded}' if encoded else '?'
