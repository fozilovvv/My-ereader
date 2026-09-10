"""Подбор жанров по метаданным книги.

В EPUB жанры лежат в тегах <dc:subject> («Science fiction», «Horror tales»),
в FB2 — в <genre> кодами вроде «sf_fantasy» или «det_classic». Модуль
переводит эту разноголосицу в коды нашего справочника (см. reader/genres.py).

Возвращаются именно КОДЫ, а не названия: какое название показать —
русское или английское — решается позже, по языку самой книги.
"""

import re

# Коды жанров FB2. Ищем самый длинный подходящий префикс,
# поэтому «sf_fantasy» найдётся раньше, чем «sf».
FB2_GENRES = {
    'sf_fantasy': 'fantasy',
    'sf_horror': 'horror',
    'sf': 'scifi',
    'fantasy': 'fantasy',
    'det': 'detective',
    'thriller': 'thriller',
    'adv': 'adventure',
    'literature_classics': 'classics',
    'literature_18': 'classics',
    'literature_19': 'classics',
    'literature_20': 'modern-prose',
    'literature': 'modern-prose',
    'foreign_detective': 'detective',
    'foreign_adventure': 'adventure',
    'foreign_fantasy': 'fantasy',
    'foreign_sf': 'scifi',
    'foreign_antique': 'classics',
    'foreign_children': 'children',
    'foreign_language': 'education',
    'foreign_psychology': 'psychology',
    'foreign_business': 'business',
    'foreign_prose': 'modern-prose',
    'foreign': 'modern-prose',
    'russian_contemporary': 'modern-prose',
    'russian_fantasy': 'fantasy',
    'nonf_biography': 'biography',
    'nonf_publicism': 'nonfiction',
    'nonf': 'nonfiction',
    'prose_classic': 'classics',
    'prose_history': 'history',
    'prose_contemporary': 'modern-prose',
    'prose': 'modern-prose',
    'antique': 'classics',
    'poetry': 'poetry',
    'poem': 'poetry',
    'dramaturgy': 'drama',
    'love': 'romance',
    'child': 'children',
    'humor': 'humour',
    'religion': 'religion',
    'sci_philosophy': 'philosophy',
    'sci_politics': 'politics',
    'sci_psychology': 'psychology',
    'sci_business': 'business',
    'sci_tech': 'technology',
    'sci_history': 'history',
    'sci_culture': 'nonfiction',
    'sci_religion': 'religion',
    'sci': 'science',
    'comp': 'technology',
    'ref': 'reference',
    'nonfiction': 'nonfiction',
    'design': 'nonfiction',
}

# Свободный текст жанра. Порядок важен: конкретное раньше общего, иначе
# «science fiction» поймалось бы правилом «science» и стало бы наукой.
TEXT_RULES = [
    ('science fiction', 'scifi'),
    ('научная фантаст', 'scifi'),
    ('фантастика', 'scifi'),
    ('fantasy', 'fantasy'),
    ('фэнтези', 'fantasy'),

    ('fairy tale', 'children'),
    ('сказк', 'children'),
    ('juvenile', 'children'),
    ('children', 'children'),
    ('детск', 'children'),

    ('horror', 'horror'),
    ('gothic', 'horror'),
    ('ужас', 'horror'),
    ('thriller', 'thriller'),
    ('suspense', 'thriller'),
    ('триллер', 'thriller'),

    ('detective', 'detective'),
    ('mystery', 'detective'),
    ('crime', 'detective'),
    ('детектив', 'detective'),

    ('adventure', 'adventure'),
    ('sea stories', 'adventure'),
    ('приключен', 'adventure'),

    ('love stories', 'romance'),
    ('romance', 'romance'),
    ('courtship', 'romance'),
    ('роман о любви', 'romance'),

    ('drama', 'drama'),
    ('tragedies', 'drama'),
    ('comedies', 'drama'),
    ('пьес', 'drama'),
    ('драматург', 'drama'),

    ('poetry', 'poetry'),
    ('poems', 'poetry'),
    ('epic', 'poetry'),
    ('поэзия', 'poetry'),
    ('стихотворен', 'poetry'),

    ('humorous', 'humour'),
    ('humour', 'humour'),
    ('humor', 'humour'),
    ('satire', 'humour'),
    ('юмор', 'humour'),

    ('mythology', 'mythology'),
    ('folklore', 'mythology'),
    ('folk literature', 'mythology'),
    ('legends', 'mythology'),
    ('folk tales', 'mythology'),
    ('мифолог', 'mythology'),
    ('фольклор', 'mythology'),

    ('biography', 'biography'),
    ('autobiograph', 'biography'),
    ('memoir', 'biography'),
    ('correspondence', 'biography'),
    ('биограф', 'biography'),
    ('мемуар', 'biography'),

    ('psycholog', 'psychology'),
    ('психолог', 'psychology'),

    ('philosophy', 'philosophy'),
    ('ethics', 'philosophy'),
    ('free thought', 'philosophy'),
    ('logic', 'philosophy'),
    ('философ', 'philosophy'),

    ('political science', 'politics'),
    ('constitution', 'politics'),
    ('state, the', 'politics'),
    ('government', 'politics'),
    ('politics', 'politics'),
    ('политик', 'politics'),

    ('bible', 'religion'),
    ('religio', 'religion'),
    ('theolog', 'religion'),
    ('church', 'religion'),
    ('koran', 'religion'),
    ('религи', 'religion'),

    ('business', 'business'),
    ('economic', 'business'),
    ('бизнес', 'business'),

    ('computer', 'technology'),
    ('technolog', 'technology'),
    ('engineering', 'technology'),
    ('программир', 'technology'),

    ('dictionar', 'reference'),
    ('encyclopedia', 'reference'),
    ('словар', 'reference'),
    ('справочник', 'reference'),

    ('textbook', 'education'),
    ('education', 'education'),
    ('study and teaching', 'education'),
    ('учебн', 'education'),

    ('history', 'history'),
    ('historical', 'history'),
    ('world war', 'history'),
    ('civil war', 'history'),
    ('military', 'history'),
    ('campaigns', 'history'),
    ('revolution', 'history'),
    ('война', 'history'),
    ('antiquities', 'history'),
    ('stone age', 'history'),
    ('assassination', 'history'),
    ('истори', 'history'),

    ('sociolog', 'science'),
    ('manners and customs', 'science'),
    ('anthropolog', 'science'),
    ('natural history', 'science'),
    ('mathematic', 'science'),
    ('astronom', 'science'),
    ('наука', 'science'),

    ('classic', 'classics'),
    ('классик', 'classics'),

    ('didactic fiction', 'modern-prose'),
    ('domestic fiction', 'modern-prose'),
    ('psychological fiction', 'psychology'),
]


# Второй уровень: пометки о ФОРМЕ произведения, а не о жанре.
# На Project Gutenberg тема книги часто записана рубрикой вроде
# «Russia -- Social life and customs -- Fiction»: жанра в ней нет, зато
# в конце стоит форма. Такие правила применяем, только если правила
# первого уровня не нашли ничего — иначе «Psychological fiction»
# превратилось бы в классику и потеряло бы точный жанр.
FALLBACK_RULES = [
    ('short stories', 'classics'),
    ('short story', 'classics'),
    ('social life and customs', 'history'),
    ('essays', 'nonfiction'),
    ('letters', 'biography'),
    ('diaries', 'biography'),
    ('sermons', 'religion'),
    ('travel', 'nonfiction'),
    ('description and travel', 'nonfiction'),
    ('juvenile literature', 'children'),
    ('fiction', 'classics'),
    ('литература', 'classics'),
    ('рассказы', 'classics'),
]


def _mentions(value: str, keyword: str) -> bool:
    """Встречается ли ключевое слово как НАЧАЛО слова, а не любой подстрокой.

    Без границы слова «logic» находился внутри «psychological», и роман
    попадал в философию. При этом сопоставление по началу сохраняется:
    «psycholog» по-прежнему ловит и psychology, и psychological.
    """
    return re.search(r'\b' + re.escape(keyword), value) is not None


def match(subjects) -> set:
    """Список жанров из файла -> набор кодов нашего справочника."""
    found = set()

    for raw in subjects or []:
        value = str(raw).strip().lower()
        if not value:
            continue

        # Как код FB2 разбираем только то, что на код и похоже: одно слово,
        # либо с подчёркиванием, либо точно совпадающее со справочником.
        # Без этой проверки «Scientists -- Fiction» опознавалось бы по началу
        # «sci» как научная литература и не доходило бы до текстовых правил.
        looks_like_code = ' ' not in value and ('_' in value or value in FB2_GENRES)
        if looks_like_code:
            code_hit = max(
                (code for code in FB2_GENRES if value.startswith(code)),
                key=len,
                default=None,
            )
            if code_hit:
                found.add(FB2_GENRES[code_hit])
                continue

        # Иначе ищем ключевые слова в свободном тексте.
        for keyword, genre_code in TEXT_RULES:
            if _mentions(value, keyword):
                found.add(genre_code)

    if found:
        return found

    # Точного жанра не нашлось — пробуем определить хотя бы форму.
    for raw in subjects or []:
        value = str(raw).strip().lower()
        for keyword, genre_code in FALLBACK_RULES:
            if _mentions(value, keyword):
                found.add(genre_code)

    return found
