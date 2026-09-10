"""Очистка HTML из книг.

Внутри EPUB лежит произвольный HTML от неизвестного автора: там может быть
<script>, реклама, кривая вёрстка. Мы пропускаем его через «белый список»:
разрешённые теги остаются, всё остальное превращается в обычный текст.
"""
from html import escape
from html.parser import HTMLParser

# Разрешаем только теги, осмысленные для книги.
ALLOWED_TAGS = {
    'p', 'br', 'hr', 'div', 'span', 'section', 'blockquote',
    'em', 'i', 'strong', 'b', 'u', 's', 'sup', 'sub', 'small', 'cite', 'q',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'a', 'code', 'pre', 'figure', 'figcaption',
}
HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
VOID_TAGS = {'br', 'hr'}

# Эти теги вырезаем ВМЕСТЕ с содержимым — их текст не нужен читателю.
DROP_WITH_CONTENT = {'script', 'style', 'head', 'title', 'noscript', 'iframe', 'object', 'svg'}

# Атрибуты: всё лишнее (class, style, onclick) отбрасываем.
ALLOWED_ATTRS = {'a': {'href'}}
SAFE_URL_PREFIXES = ('http://', 'https://', 'mailto:', '#')


class _Sanitizer(HTMLParser):
    """Проходит по HTML и собирает заново только разрешённые куски."""

    def __init__(self, drop_first_heading: bool = False):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.open_tags: list[str] = []
        self.skip_depth = 0

        # Попутно вытаскиваем первый заголовок — он станет названием главы.
        self.heading = ''
        self._heading_parts: list[str] = []
        self._in_heading = False
        self._heading_done = False

        # Если название главы мы и так покажем сверху сами, заголовок из
        # книги можно не выводить — иначе он задвоится на экране.
        self.drop_first_heading = drop_first_heading
        self._dropping = False

    # --- служебное ---------------------------------------------------

    @staticmethod
    def _render_attrs(tag: str, attrs) -> str:
        allowed = ALLOWED_ATTRS.get(tag, frozenset())
        parts = []
        for name, value in attrs:
            if name not in allowed or not value:
                continue
            # Блокируем javascript:... — классический способ внедрить код.
            if name == 'href' and not value.lower().startswith(SAFE_URL_PREFIXES):
                continue
            parts.append(f' {name}="{escape(value, quote=True)}"')
        return ''.join(parts)

    # --- обработчики HTMLParser --------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip_depth += 1
            return
        if self.skip_depth or self._dropping:
            return

        if tag in HEADING_TAGS and not self._heading_done:
            self._in_heading = True
            if self.drop_first_heading:
                self._dropping = True      # сам заголовок в вывод не попадёт
                return

        if tag not in ALLOWED_TAGS:
            return

        self.out.append(f'<{tag}{self._render_attrs(tag, attrs)}>')
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if not self.skip_depth and tag in VOID_TAGS:
            self.out.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        if self._in_heading and tag in HEADING_TAGS:
            self._in_heading = False
            self._heading_done = True
            self.heading = ' '.join(''.join(self._heading_parts).split())
            if self._dropping:
                self._dropping = False
                return
        elif self._dropping:
            return

        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return

        # Закрываем всё, что осталось открытым внутри — так чинится кривая вёрстка.
        if tag in self.open_tags:
            while self.open_tags:
                open_tag = self.open_tags.pop()
                self.out.append(f'</{open_tag}>')
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self._in_heading:
            self._heading_parts.append(data)
        if self._dropping:
            return
        self.out.append(escape(data, quote=False))

    # --- результат ----------------------------------------------------

    def result(self) -> str:
        while self.open_tags:
            self.out.append(f'</{self.open_tags.pop()}>')
        return ''.join(self.out).strip()


def clean_html(raw: str, drop_first_heading: bool = False) -> tuple[str, str]:
    """Возвращает пару: (безопасный HTML, заголовок из первого <h1>–<h6>).

    drop_first_heading=True убирает этот заголовок из текста: читалка
    всё равно печатает название главы сверху, и в книге оно задваивалось.
    """
    parser = _Sanitizer(drop_first_heading=drop_first_heading)
    parser.feed(raw)
    parser.close()
    return parser.result(), parser.heading


class _HeadingScanner(HTMLParser):
    """Быстрый предварительный проход: собирает текст всех заголовков файла.

    Нужен, чтобы решить, резать ли документ на несколько глав, ДО того как
    начнётся полноценный разбор — так решение принимается один раз и
    заранее, а не на лету по ходу парсинга.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings: list[str] = []
        self._in_heading = False
        self._buffer: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if self._in_heading:
            # <br> внутри заголовка — разделитель строк: издания часто кладут
            # подпись к иллюстрации и настоящий номер главы в один <h2>,
            # одно под другим. Без разбивки по строкам они бы склеились
            # в одну фразу, не похожую ни на что.
            if tag == 'br':
                self._buffer.append('\n')
            return
        if tag in HEADING_TAGS:
            self._in_heading = True
            self._buffer = []

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if self._in_heading and tag in HEADING_TAGS:
            self._in_heading = False
            raw = ''.join(self._buffer)
            for line in raw.split('\n'):
                cleaned = ' '.join(line.split())
                if cleaned:
                    self.headings.append(cleaned)

    def handle_data(self, data):
        if self._in_heading and not self._skip_depth:
            self._buffer.append(data)

    @classmethod
    def scan(cls, raw: str) -> list[str]:
        """Возвращает отдельные СТРОКИ заголовков, а не заголовки целиком.

        Так «Подпись к картинке \\n CHAPTER LVII.» превращается в две
        отдельные строки, и chapter-проверка видит вторую из них саму по
        себе, а не склеенную с посторонним текстом.
        """
        parser = cls()
        parser.feed(raw)
        parser.close()
        return parser.headings


class _ChapterSplitter(HTMLParser):
    """Режет один HTML-документ на несколько глав по заголовкам-разделителям.

    Обычно один файл EPUB — это одна глава. Но в некоторых изданиях (часто
    встречается на Project Gutenberg) один файл содержит сразу несколько
    глав подряд, без разбивки на отдельные файлы — только заголовки внутри
    вида «CHAPTER XX.» отделяют их друг от друга.

    Копирует белый список тегов и защиту от кривой вёрстки у _Sanitizer, но
    решение по каждому заголовку откладывает до его закрывающего тега: если
    текст похож на начало главы (is_chapter_heading) — заголовок становится
    границей и заголовком новой главы, сам в текст не попадая. Если не
    похож (например, подпись под иллюстрацией) — рендерится на месте как
    обычный подзаголовок, вместе с остальным телом.
    """

    def __init__(self, is_chapter_heading):
        super().__init__(convert_charrefs=True)
        self.is_chapter_heading = is_chapter_heading
        self.segments: list[dict] = []

        self._out: list[str] = []
        self._open_tags: list[str] = []
        self._title = ''
        self.skip_depth = 0

        self._in_heading = False
        self._heading_tag = ''
        self._heading_parts: list[str] = []

    def _flush(self):
        """Закрывает текущий сегмент. Пустой сегмент без заголовка не сохраняем."""
        while self._open_tags:
            self._out.append(f'</{self._open_tags.pop()}>')
        html = ''.join(self._out).strip()
        self._out = []
        if has_text(html) or self._title:
            self.segments.append({
                'title': self._title,
                'content': html,
                # Кусок без заголовка в начале файла — это почти всегда хвост
                # предыдущей главы (вклейка с иллюстрацией, концовка страницы).
                # Помечаем его, чтобы вызывающий код мог не заводить под него
                # отдельную главу в оглавлении.
                'continuation': not self._title,
            })

    def _heading_lines(self) -> list[str]:
        """Текст заголовка, разбитый на строки по <br>.

        Издания часто кладут в один <h2> подпись к иллюстрации и настоящий
        номер главы, разделив их переносами. Разбор построчно позволяет
        узнать «CHAPTER LVII.» отдельно от соседней подписи.
        """
        raw = ''.join(self._heading_parts)
        lines = [' '.join(line.split()) for line in raw.split('\n')]
        return [line for line in lines if line]

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        # Внутри заголовка вложенную разметку не выводим: из него нам нужен
        # только текст. Иначе пустые <span> и <a> утекли бы в тело главы.
        if self._in_heading:
            if tag == 'br':
                self._heading_parts.append('\n')
            return

        if tag in HEADING_TAGS:
            # Рендерить или дропать — решится только когда заголовок закроется
            # и станет известен его полный текст (см. handle_endtag).
            self._in_heading = True
            self._heading_tag = tag
            self._heading_parts = []
            return

        if tag not in ALLOWED_TAGS:
            return
        self._out.append(f'<{tag}{_Sanitizer._render_attrs(tag, attrs)}>')
        if tag not in VOID_TAGS:
            self._open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if self.skip_depth:
            return
        if self._in_heading:
            if tag == 'br':
                self._heading_parts.append('\n')
            return
        if tag in VOID_TAGS:
            self._out.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return

        if self._in_heading:
            # Закрывающие теги вложенной разметки внутри заголовка игнорируем:
            # открывающие мы тоже не выводили, закрывать нечего.
            if tag not in HEADING_TAGS:
                return

            self._in_heading = False
            lines = self._heading_lines()

            # Берём ПОСЛЕДНЮЮ подходящую строку: настоящий номер главы стоит
            # после подписи к иллюстрации, а не перед ней.
            chapter_line = ''
            for line in lines:
                if self.is_chapter_heading(line):
                    chapter_line = line

            if chapter_line:
                self._flush()                 # закрываем предыдущую главу
                self._title = chapter_line    # и начинаем новую с этим заголовком
            elif lines:
                # Не похоже на начало главы — обычный подзаголовок внутри текста.
                text = escape(' '.join(lines))
                self._out.append(f'<{self._heading_tag}>{text}</{self._heading_tag}>')
            return

        if tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return

        if tag in self._open_tags:
            while self._open_tags:
                open_tag = self._open_tags.pop()
                self._out.append(f'</{open_tag}>')
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self._in_heading:
            self._heading_parts.append(data)
            return
        self._out.append(escape(data, quote=False))

    def result(self) -> list[dict]:
        self._flush()
        return self.segments


def split_html(raw: str, is_chapter_heading) -> list[dict]:
    """Разбирает HTML-файл на одну или несколько «глав».

    Сначала смотрим, есть ли в файле хоть один заголовок, похожий на
    начало главы (is_chapter_heading). Если нет — файл ведёт себя как
    раньше: одна глава, названная по первому попавшемуся заголовку любого
    вида (clean_html). Если есть — режем документ по таким заголовкам,
    а всё остальное (подписи к иллюстрациям, подзаголовки) остаётся
    обычным текстом внутри той главы, где встретилось.
    """
    if not any(is_chapter_heading(text) for text in _HeadingScanner.scan(raw)):
        html, title = clean_html(raw, drop_first_heading=True)
        # Файл целиком = одна глава, приклеивать его к предыдущей нельзя:
        # иначе книга без единого заголовка слиплась бы в одну огромную главу.
        return [{'title': title, 'content': html, 'continuation': False}]

    parser = _ChapterSplitter(is_chapter_heading)
    parser.feed(raw)
    parser.close()
    return parser.result()


def text_of(html: str) -> str:
    """HTML -> обычный текст с нормализованными пробелами."""
    return _TextOnly.extract(html)


def has_text(html: str) -> bool:
    """Есть ли в куске HTML хоть какой-то осмысленный текст?"""
    stripped = _TextOnly.extract(html)
    return len(stripped) > 20


class _TextOnly(HTMLParser):
    """Вспомогательный парсер: выкидывает теги, оставляет текст."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []

    def handle_data(self, data):
        self.chunks.append(data)

    @classmethod
    def extract(cls, html: str) -> str:
        parser = cls()
        parser.feed(html)
        parser.close()
        return ' '.join(''.join(parser.chunks).split())
