"""Данные, которые нужны в шапке на каждой странице."""
from .models import ActivityDay, BookRequest


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


def heartbeat_settings(request):
    """Интервал сигнала присутствия — из модели, а не из числа в шаблоне.

    Одно значение задано в ActivityDay.HEARTBEAT_SECONDS: по нему сервер
    считает время и по нему же браузер шлёт сигналы. Держать два одинаковых
    числа в Python и в JavaScript — верный способ однажды их рассогласовать
    и получить статистику, которая врёт вдвое.
    """
    return {'heartbeat_seconds': ActivityDay.HEARTBEAT_SECONDS}
