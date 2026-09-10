from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Book, BookRequest, Category, Chapter, Quote, ReadingProgress, Shelf
from .parsing import ParseError, import_book

admin.site.site_header = 'Библиотека — панель управления'
admin.site.site_title = 'Библиотека'
admin.site.index_title = 'Управление каталогом'


class ChapterInline(admin.TabularInline):
    """Список глав прямо на странице книги."""
    model = Chapter
    extra = 0
    fields = ('order', 'title', 'char_count')
    readonly_fields = ('char_count',)
    ordering = ('order',)
    show_change_link = True


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('cover_preview', 'title', 'author', 'status', 'chapters_count', 'created_at')
    list_display_links = ('cover_preview', 'title')
    list_filter = ('status', 'language', 'created_at')
    search_fields = ('title', 'author', 'description')
    readonly_fields = ('created_at', 'slug', 'parse_error')
    inlines = [ChapterInline]
    actions = ['parse_selected_books']
    filter_horizontal = ('categories',)
    fieldsets = (
        ('Файл', {'fields': ('source_file', 'status', 'parse_error')}),
        ('Описание', {'fields': ('title', 'author', 'description', 'language', 'cover', 'categories')}),
        ('Служебное', {'fields': ('slug', 'uploaded_by', 'created_at'), 'classes': ('collapse',)}),
    )

    @admin.action(description='Разобрать файл на главы')
    def parse_selected_books(self, request, queryset):
        for book in queryset:
            try:
                created = import_book(book)
            except ParseError as error:
                book.status = Book.Status.ERROR
                book.parse_error = str(error)
                book.save(update_fields=['status', 'parse_error'])
                self.message_user(request, f'«{book.title}»: {error}', messages.ERROR)
            except Exception as error:  # непредвиденное — тоже показываем, а не роняем админку
                book.status = Book.Status.ERROR
                book.parse_error = f'{type(error).__name__}: {error}'
                book.save(update_fields=['status', 'parse_error'])
                self.message_user(request, f'«{book.title}»: сбой разбора — {error}', messages.ERROR)
            else:
                self.message_user(request, f'«{book.title}»: создано глав — {created}', messages.SUCCESS)

    @admin.display(description='Глав')
    def chapters_count(self, obj):
        return obj.chapters.count()

    @admin.display(description='Обложка')
    def cover_preview(self, obj):
        if obj.cover:
            return format_html('<img src="{}" style="height:48px;border-radius:4px">', obj.cover.url)
        return '—'


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'book', 'order', 'char_count')
    list_filter = ('book',)
    search_fields = ('title', 'content')
    readonly_fields = ('char_count',)


@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'chapter', 'percent', 'updated_at')
    list_filter = ('user', 'book')
    readonly_fields = ('updated_at',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'language', 'code', 'position', 'books_count')
    list_filter = ('language',)
    list_editable = ('position',)
    search_fields = ('name', 'code')
    readonly_fields = ('slug',)

    @admin.display(description='Книг')
    def books_count(self, obj):
        return obj.books.count()


@admin.register(Shelf)
class ShelfAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'status', 'is_favorite', 'updated_at')
    list_filter = ('status', 'is_favorite', 'user')
    search_fields = ('book__title', 'user__username')
    readonly_fields = ('updated_at',)


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'book', 'chapter', 'created_at')
    list_filter = ('user', 'book')
    search_fields = ('text', 'note')
    readonly_fields = ('created_at',)


@admin.register(BookRequest)
class BookRequestAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'status', 'user', 'created_at')
    list_filter = ('status', 'created_at')
    list_editable = ('status',)
    search_fields = ('title', 'author', 'genre', 'comment')
    readonly_fields = ('created_at', 'user', 'title', 'author', 'genre', 'comment')
    fieldsets = (
        ('Заявка', {'fields': ('title', 'author', 'genre', 'comment', 'user', 'created_at')}),
        ('Обработка', {'fields': ('status', 'admin_note')}),
    )

    @admin.action(description='Пометить как «В работе»')
    def mark_in_work(self, request, queryset):
        updated = queryset.update(status=BookRequest.Status.IN_WORK)
        self.message_user(request, f'Заказов обновлено: {updated}', messages.SUCCESS)

    @admin.action(description='Пометить как «Добавлена»')
    def mark_done(self, request, queryset):
        updated = queryset.update(status=BookRequest.Status.DONE)
        self.message_user(request, f'Заказов обновлено: {updated}', messages.SUCCESS)

    actions = ['mark_in_work', 'mark_done']
