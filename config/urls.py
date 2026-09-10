"""Главная карта адресов проекта."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from reader import views as reader_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Переключатель языка: запоминает выбор в сессии и возвращает обратно.
    path('i18n/', include('django.conf.urls.i18n')),

    # Своя страница регистрации + готовые страницы Django:
    # /accounts/login/, /accounts/logout/, смена и сброс пароля.
    path('accounts/signup/', reader_views.signup, name='signup'),
    path('accounts/', include('django.contrib.auth.urls')),

    path('', include('reader.urls')),   # всё остальное отдаём приложению reader
]

# В режиме разработки Django сам раздаёт загруженные файлы (книги, обложки).
# На боевом сервере этим займётся nginx.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
