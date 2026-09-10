"""Заглушка AI-ответов для работы без ключа API.

Задача файла — не изображать искусственный интеллект, а дать фронтенду
реалистичные данные: текст переменной длины, задержку ответа, режим ошибки.
Когда появится ключ, весь этот модуль перестанет вызываться сам собой.
"""
import re
import textwrap
import time

from django.conf import settings

NOTE = '[демо-режим] Ключ API не подключён — ответ собран локально, без обращения к модели.'


def answer(action: str, fragment: str, context: str = '') -> str:
    """Возвращает правдоподобный ответ той же формы, что и настоящий."""
    time.sleep(settings.AI_MOCK_DELAY)      # имитируем задержку сети

    if action == 'translate':
        return _translate(fragment, context)
    if action == 'explain':
        return _explain(fragment, context)
    return _summarize(fragment)


def _translate(fragment: str, context: str) -> str:
    words = fragment.split()
    lines = [
        f'**{fragment}**',
        f'Слов: {len(words)}, символов: {len(fragment)}.',
        'Здесь появится перевод, часть речи и значение в контексте.',
    ]
    if context:
        lines.append(f'Контекст: «{textwrap.shorten(context, 140, placeholder="…")}»')
    lines.append(NOTE)
    return '\n'.join(lines)


def _explain(fragment: str, context: str) -> str:
    lines = [
        f'**Разбор фрагмента** ({len(fragment)} символов)',
        f'«{textwrap.shorten(fragment, 200, placeholder="…")}»',
        'Здесь появится объяснение: что происходит во фрагменте, на какие реалии '
        'он опирается и какой в нём подтекст.',
        NOTE,
    ]
    return '\n'.join(lines)


def _summarize(text: str) -> str:
    """Наивная выжимка: берём первые предложения равномерно по всей главе.

    Это не пересказ, а механическая выборка — но объём и вид у неё такие же,
    как у настоящего ответа, и на ней удобно отлаживать интерфейс.
    """
    sentences = [
        part.strip()
        for part in re.split(r'(?<=[.!?…])\s+', text)
        if len(part.strip()) > 40
    ]

    if not sentences:
        return 'В главе слишком мало текста для выжимки.\n' + NOTE

    step = max(1, len(sentences) // 5)
    picked = sentences[::step][:5]

    bullets = '\n'.join(
        f'• {textwrap.shorten(sentence, 150, placeholder="…")}' for sentence in picked
    )
    return f'**Ключевые места главы**\n{bullets}\n{NOTE}'
