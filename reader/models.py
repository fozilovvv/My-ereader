from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from . import search


class Category(models.Model):
    """Жанр книги: «Фантастика», «Нон-фикшн».

    Один и тот же жанр существует в двух вариантах — русском и английском.
    Их связывает общий code: по нему парсер находит жанр независимо от
    языка, а книге достаётся вариант на её собственном языке.
    """

    class Language(models.TextChoices):
        RU = 'ru', 'Русские'
        EN = 'en', 'Английские'

    code = models.SlugField('Код жанра', max_length=40, default='other')
    language = models.CharField('Язык', max_length=5, choices=Language, default=Language.RU)

    name = models.CharField('Название', max_length=80)
    slug = models.SlugField('Адрес', max_length=90, unique=True, blank=True, allow_unicode=True)
    position = models.PositiveIntegerField('Порядок в списке', default=100)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['language', 'position', 'name']
        constraints = [
            models.UniqueConstraint(fields=['code', 'language'], name='unique_category_per_language'),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True) or 'category'
        super().save(*args, **kwargs)


class Book(models.Model):
    """Одна книга в библиотеке."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает разбора'
        READY = 'ready', 'Готова к чтению'
        ERROR = 'error', 'Ошибка разбора'

    # blank=True: при загрузке EPUB/FB2 название подтянется из файла само.
    title = models.CharField('Название', max_length=255, blank=True)
    author = models.CharField('Автор', max_length=255, blank=True)
    description = models.TextField('Описание', blank=True)
    # Пусто = язык ещё не определён. Значение по умолчанию 'ru' здесь было
    # ошибкой: поле никогда не выглядело пустым, и настоящий язык из
    # метаданных файла в него не попадал.
    language = models.CharField('Язык', max_length=10, blank=True, default='')

    cover = models.ImageField('Обложка', upload_to='covers/', blank=True, null=True)
    source_file = models.FileField('Файл книги', upload_to='books/')

    # ManyToMany: у книги много категорий, у категории много книг.
    # Django создаст для этой связи отдельную служебную таблицу.
    categories = models.ManyToManyField(
        Category, verbose_name='Категории', blank=True, related_name='books',
    )

    slug = models.SlugField('Адрес', max_length=280, unique=True, blank=True, allow_unicode=True)
    status = models.CharField('Статус', max_length=20, choices=Status, default=Status.PENDING)
    parse_error = models.TextField('Текст ошибки', blank=True)

    # Денормализация: сумма символов всех глав. Можно было бы считать
    # агрегатом при каждом запросе, но объём книги меняется только при
    # разборе файла — дешевле посчитать один раз и хранить.
    total_chars = models.PositiveIntegerField('Объём, символов', default=0)

    # Название и автор в нижнем регистре — по этому полю идёт поиск.
    # db_index: поле участвует в каждом запросе каталога.
    search_text = models.CharField('Поисковая строка', max_length=520, blank=True, db_index=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Кто загрузил',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='books',
    )
    created_at = models.DateTimeField('Добавлена', auto_now_add=True)

    class Meta:
        verbose_name = 'Книга'
        verbose_name_plural = 'Книги'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} — {self.author}' if self.author else self.title

    def get_absolute_url(self):
        """Django использует этот метод для кнопки «Смотреть на сайте» в админке."""
        return reverse('reader:book_detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        # Поисковую строку пересобираем при каждом сохранении: изменилось
        # название — сразу изменился и поиск, забыть об этом невозможно.
        self.search_text = search.normalize(f'{self.title} {self.author}')[:520]

        # Название намеренно НЕ подставляем из имени файла: сначала своё слово
        # скажут метаданные книги (см. reader/parsing). Иначе имя файла заняло бы
        # поле и настоящее название из EPUB уже некуда было бы записать.
        if not self.slug:
            self.slug = self._make_unique_slug()
        super().save(*args, **kwargs)

    def _make_unique_slug(self):
        base = slugify(self.title, allow_unicode=True)
        if not base and self.source_file:
            base = slugify(Path(self.source_file.name).stem, allow_unicode=True)
        base = base or 'book'
        slug, counter = base, 2
        while Book.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{counter}'
            counter += 1
        return slug


class Chapter(models.Model):
    """Одна глава книги. Читалка показывает по одной главе за раз."""

    book = models.ForeignKey(
        Book, verbose_name='Книга', on_delete=models.CASCADE, related_name='chapters',
    )
    order = models.PositiveIntegerField('Порядковый номер', default=0)
    title = models.CharField('Заголовок', max_length=255, blank=True)
    content = models.TextField('Текст главы (HTML)')
    char_count = models.PositiveIntegerField('Символов', default=0)

    class Meta:
        verbose_name = 'Глава'
        verbose_name_plural = 'Главы'
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['book', 'order'], name='unique_chapter_order'),
        ]

    def __str__(self):
        return self.title or f'Глава {self.order + 1}'

    def save(self, *args, **kwargs):
        self.char_count = len(self.content)
        super().save(*args, **kwargs)


class ReadingProgress(models.Model):
    """Где именно пользователь остановился в конкретной книге."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Пользователь',
        on_delete=models.CASCADE, related_name='reading_progress',
    )
    book = models.ForeignKey(
        Book, verbose_name='Книга', on_delete=models.CASCADE, related_name='progress_entries',
    )
    chapter = models.ForeignKey(
        Chapter, verbose_name='Глава', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='progress_entries',
    )
    scroll_ratio = models.FloatField('Прокрутка внутри главы (0..1)', default=0.0)
    percent = models.FloatField('Прочитано книги, %', default=0.0)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Прогресс чтения'
        verbose_name_plural = 'Прогресс чтения'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'book'], name='unique_progress_per_book'),
        ]

    def __str__(self):
        return f'{self.user} → {self.book} ({self.percent:.0f}%)'


class Shelf(models.Model):
    """Личное отношение пользователя к книге: статус и избранное.

    Почему отдельно от ReadingProgress: прогресс пишет машина (сама, при
    прокрутке), а полку — человек, осознанным действием. Разные источники
    правды не стоит держать в одной строке: иначе автосохранение прогресса
    рано или поздно затрёт то, что пользователь выбрал руками.
    """

    # С какого процента книга считается дочитанной.
    # Одно значение на весь проект: и для автостатуса, и для полки «Продолжить».
    FINISHED_PERCENT = 99

    class Status(models.TextChoices):
        PLANNED = 'planned', 'В планах'
        READING = 'reading', 'Читаю сейчас'
        FINISHED = 'finished', 'Прочитано'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Пользователь',
        on_delete=models.CASCADE, related_name='shelf',
    )
    book = models.ForeignKey(
        Book, verbose_name='Книга', on_delete=models.CASCADE, related_name='shelf_entries',
    )
    # Пусто — книги нет ни в одном статусе (например, она только в избранном).
    status = models.CharField('Статус', max_length=20, choices=Status, blank=True)
    is_favorite = models.BooleanField('В избранном', default=False)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)

    class Meta:
        verbose_name = 'Полка'
        verbose_name_plural = 'Полки пользователей'
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['user', 'book'], name='unique_shelf_per_book'),
        ]

    def __str__(self):
        label = self.get_status_display() if self.status else 'без статуса'
        return f'{self.user} · {self.book} — {label}'


class Quote(models.Model):
    """Цитата из книги с личной заметкой пользователя."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Пользователь',
        on_delete=models.CASCADE, related_name='quotes',
    )
    book = models.ForeignKey(
        Book, verbose_name='Книга', on_delete=models.CASCADE, related_name='quotes',
    )
    # SET_NULL, а не CASCADE: при повторном разборе книги главы пересоздаются,
    # и цитаты не должны исчезать вместе с ними. Книга и текст останутся.
    chapter = models.ForeignKey(
        Chapter, verbose_name='Глава', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quotes',
    )

    text = models.TextField('Текст цитаты')
    note = models.TextField('Заметка', blank=True)
    scroll_ratio = models.FloatField('Позиция в главе (0..1)', default=0.0)
    created_at = models.DateTimeField('Сохранена', auto_now_add=True)

    class Meta:
        verbose_name = 'Цитата'
        verbose_name_plural = 'Цитаты'
        ordering = ['-created_at']
        indexes = [
            # По этой паре идёт выборка цитат при открытии главы.
            models.Index(fields=['user', 'chapter']),
        ]

    def __str__(self):
        preview = self.text[:60]
        return f'{preview}…' if len(self.text) > 60 else preview


class BookRequest(models.Model):
    """Заявка читателя: какую книгу он хочет видеть в библиотеке."""

    class Status(models.TextChoices):
        NEW = 'new', 'Новая'
        IN_WORK = 'in_work', 'В работе'
        DONE = 'done', 'Добавлена'
        REJECTED = 'rejected', 'Отклонена'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name='Заказчик',
        on_delete=models.SET_NULL, null=True, blank=True, related_name='book_requests',
    )

    # Все три поля необязательны по отдельности, но форма требует хотя бы одно:
    # человек может помнить только автора или только жанр.
    title = models.CharField('Название книги', max_length=255, blank=True)
    author = models.CharField('Автор', max_length=255, blank=True)
    genre = models.CharField('Жанр или тема', max_length=255, blank=True)
    comment = models.TextField('Комментарий', blank=True)

    status = models.CharField('Статус', max_length=20, choices=Status, default=Status.NEW)
    admin_note = models.TextField('Заметка администратора', blank=True)
    created_at = models.DateTimeField('Создана', auto_now_add=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        parts = [part for part in (self.title, self.author, self.genre) if part]
        return ' · '.join(parts) or f'Заказ №{self.pk}'


class CatalogEntry(models.Model):
    """Запись из каталога Project Gutenberg — витрина для добавления книг.

    Каталог скачивается одним файлом и хранится у нас (см. команду
    sync_catalog). Причина простая: публичный поиск Gutendex выполняется
    около ста секунд, а по локальной таблице — мгновенно и без сети.
    Сам файл книги скачивается уже потом, по требованию.
    """

    gutenberg_id = models.PositiveIntegerField('Номер в Gutenberg', unique=True)
    title = models.CharField('Название', max_length=500)
    authors = models.CharField('Авторы', max_length=500, blank=True)
    language = models.CharField('Язык', max_length=20, blank=True)
    subjects = models.TextField('Темы', blank=True)

    # Название и автор в нижнем регистре — по этому полю идёт поиск.
    search_text = models.CharField('Поисковая строка', max_length=1000, db_index=True)

    class Meta:
        verbose_name = 'Запись каталога'
        verbose_name_plural = 'Каталог Gutenberg'
        ordering = ['title']

    def __str__(self):
        return f'{self.title} — {self.authors}' if self.authors else self.title

    @property
    def download_url(self) -> str:
        """Прямая ссылка на EPUB. Адрес выводится из номера книги."""
        return f'https://www.gutenberg.org/cache/epub/{self.gutenberg_id}/pg{self.gutenberg_id}.epub'

    @property
    def cover_url(self) -> str:
        return (f'https://www.gutenberg.org/cache/epub/'
                f'{self.gutenberg_id}/pg{self.gutenberg_id}.cover.medium.jpg')
