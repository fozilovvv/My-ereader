"""Справочник жанров: один код — два названия.

Каждый жанр существует в двух вариантах, русском и английском. Связывает
их код: парсер книги определяет именно код, а какое название показать —
решается по языку самой книги. Так английский роман попадёт в «Classics»,
а русский — в «Классику», и в сайдбаре они лежат в разных разделах.
"""

# (код, русское название, английское название)
GENRES = [
    ('classics',     'Классика',          'Classics'),
    ('modern-prose', 'Современная проза', 'Modern prose'),
    ('scifi',        'Фантастика',        'Science fiction'),
    ('fantasy',      'Фэнтези',           'Fantasy'),
    ('detective',    'Детектив',          'Detective'),
    ('thriller',     'Триллер',           'Thriller'),
    ('horror',       'Ужасы',             'Horror'),
    ('romance',      'Романтика',         'Romance'),
    ('adventure',    'Приключения',       'Adventure'),
    ('drama',        'Драматургия',       'Drama'),
    ('poetry',       'Поэзия',            'Poetry'),
    ('humour',       'Юмор',              'Humour'),
    ('mythology',    'Мифы и фольклор',   'Myths and folklore'),
    ('children',     'Детское',           'Children'),
    ('nonfiction',   'Нон-фикшн',         'Non-fiction'),
    ('history',      'История',           'History'),
    ('biography',    'Биографии',         'Biography'),
    ('psychology',   'Психология',        'Psychology'),
    ('philosophy',   'Философия',         'Philosophy'),
    ('politics',     'Политика',          'Politics'),
    ('religion',     'Религия',           'Religion'),
    ('science',      'Наука',             'Science'),
    ('business',     'Бизнес',            'Business'),
    ('technology',   'Технологии',        'Technology'),
    ('education',    'Учебное',           'Education'),
    ('reference',    'Справочники',       'Reference'),
]

CODES = {code for code, _, _ in GENRES}


def names_by_language() -> list[tuple]:
    """Разворачивает справочник в строки таблицы: (код, язык, название, порядок)."""
    rows = []
    for position, (code, russian, english) in enumerate(GENRES, start=1):
        rows.append((code, 'ru', russian, position))
        rows.append((code, 'en', english, position))
    return rows
