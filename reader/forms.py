"""Формы приложения."""
from pathlib import Path

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Book, BookRequest
from .parsing import PARSERS

User = get_user_model()

MAX_UPLOAD_MB = 50


class SignUpForm(UserCreationForm):
    """Регистрация. Берём готовую форму Django и добавляем необязательный email."""

    email = forms.EmailField(label='Email', required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Подсказки по паролю Django пишет длинным списком — оставим самое важное.
        self.fields['password1'].help_text = 'Минимум 8 символов, не только цифры.'
        self.fields['username'].help_text = 'Латиница, цифры и символы @ . + - _'


class BookUploadForm(forms.ModelForm):
    """Загрузка книги обычным пользователем."""

    class Meta:
        model = Book
        fields = ('source_file', 'title', 'author')
        labels = {
            'source_file': 'Файл книги',
            'title': 'Название (необязательно)',
            'author': 'Автор (необязательно)',
        }
        help_texts = {
            'source_file': f'{", ".join(sorted(PARSERS))} — до {MAX_UPLOAD_MB} МБ',
            'title': 'Для EPUB и FB2 подтянется из файла само',
        }

    def clean_source_file(self):
        """Проверяем файл ДО того, как он попадёт в базу.

        Валидация в форме — правильное место для таких проверок: пользователь
        видит понятную ошибку рядом с полем, а не страницу с трассировкой.
        """
        uploaded = self.cleaned_data['source_file']

        suffix = Path(uploaded.name).suffix.lower()
        if suffix not in PARSERS:
            supported = ', '.join(sorted(PARSERS))
            raise forms.ValidationError(f'Формат «{suffix}» не поддерживается. Можно: {supported}')

        if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(f'Файл больше {MAX_UPLOAD_MB} МБ.')

        return uploaded


class BookUrlForm(forms.Form):
    """Импорт книги по прямой ссылке на файл."""

    url = forms.URLField(
        label='Ссылка на файл книги',
        widget=forms.URLInput(attrs={'placeholder': 'https://example.org/book.epub'}),
        help_text=f'Прямая ссылка на файл: {", ".join(sorted(PARSERS))}',
    )
    title = forms.CharField(label='Название (необязательно)', required=False, max_length=255)
    author = forms.CharField(label='Автор (необязательно)', required=False, max_length=255)


class BookRequestForm(forms.ModelForm):
    """Заявка на книгу, которой пока нет в библиотеке."""

    class Meta:
        model = BookRequest
        fields = ('title', 'author', 'genre', 'comment')
        labels = {
            'title': 'Название книги',
            'author': 'Автор',
            'genre': 'Жанр или тема',
            'comment': 'Комментарий',
        }
        help_texts = {
            'comment': 'Издание, перевод, язык — всё, что поможет найти нужное',
        }
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        """Хотя бы одно поле должно быть заполнено.

        Проверка живёт в clean(), а не в clean_<поле>: она смотрит сразу
        на несколько полей, а такие правила Django ждёт именно здесь.
        """
        cleaned = super().clean()
        if not any(cleaned.get(field) for field in ('title', 'author', 'genre')):
            raise forms.ValidationError(
                'Заполни хотя бы одно: название, автора или жанр — иначе заказ не найти.'
            )
        return cleaned
