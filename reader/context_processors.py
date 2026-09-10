"""Данные, которые нужны в шапке на каждой странице."""
from .models import BookRequest


def pending_orders(request):
    """Сколько новых заказов ждёт администратора.

    Контекстный процессор, а не переменная во view: шапка рисуется на
    каждой странице сайта, и повторять этот запрос в каждом view было бы
    и утомительно, и легко забыть.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not user.is_staff:
        return {}

    return {
        'pending_orders_count': BookRequest.objects.filter(
            status=BookRequest.Status.NEW,
        ).count(),
    }
