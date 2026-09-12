"""Адреса приложения reader."""
from django.urls import path

from . import views

app_name = 'reader'

urlpatterns = [
    path('', views.book_list, name='book_list'),
    path('upload/', views.book_upload, name='book_upload'),
    path('upload/url/', views.book_import_url, name='book_import_url'),

    # API для JavaScript: принимает JSON, отвечает JSON.
    path('api/progress/', views.save_progress, name='save_progress'),
    path('api/ai/', views.ai_assist, name='ai_assist'),
    path('api/shelf/', views.shelf_update, name='shelf_update'),
    path('api/search/', views.search_api, name='search_api'),
    path('api/quotes/', views.quote_create, name='quote_create'),
    path('api/quotes/<int:pk>/', views.quote_update, name='quote_update'),
    # «Я здесь»: сигнал присутствия от открытой вкладки, раз в полминуты.
    path('api/heartbeat/', views.heartbeat, name='heartbeat'),

    path('quotes/', views.quotes_list, name='quotes_list'),
    path('request/', views.book_request, name='book_request'),
    path('orders/', views.book_request_list, name='book_request_list'),
    path('catalog/', views.catalog_find, name='catalog_find'),
    path('analytics/', views.analytics, name='analytics'),

    # <str:slug>, а не <slug:slug>: встроенный конвертер slug не пропускает кириллицу,
    # а у нас адреса вида /book/хранитель-тихой-станции/
    path('book/<str:slug>/', views.book_detail, name='book_detail'),
    path('book/<str:slug>/read/<int:order>/', views.chapter_read, name='chapter_read'),
]
