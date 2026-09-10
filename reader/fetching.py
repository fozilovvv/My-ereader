"""Безопасное скачивание книги по ссылке.

Функция «сервер, сходи по этому адресу» — одна из самых опасных в вебе.
Она называется SSRF: пользователь даёт ссылку, а запрос уходит от имени
сервера, изнутри вашей сети. Через неё дотягиваются до баз данных,
админок и служебных адресов облачных провайдеров, закрытых извне.

Поэтому здесь три уровня защиты:
  1. разрешены только схемы http и https;
  2. имя хоста резолвится в IP, и каждый адрес проверяется на «внешность»;
  3. перенаправления обрабатываются вручную — каждый переход проверяется
     заново, иначе внешняя ссылка могла бы увести на 127.0.0.1.
"""
import ipaddress
import re
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BYTES = 50 * 1024 * 1024      # 50 МБ — столько же, сколько у загрузки файлом
TIMEOUT = 20                      # секунд на соединение
MAX_REDIRECTS = 5

ALLOWED_SCHEMES = {'http', 'https'}
USER_AGENT = 'PersonalLibrary/1.0 (+book import)'

# Тип содержимого -> расширение. Нужен, когда в ссылке нет имени файла.
CONTENT_TYPES = {
    'application/epub+zip': '.epub',
    'application/x-fictionbook+xml': '.fb2',
    'text/plain': '.txt',
    'application/zip': '.zip',
}


class FetchError(Exception):
    """Ссылку не удалось скачать — понятная человеку причина."""


class _NoRedirect(HTTPRedirectHandler):
    """Отключает автоматические переходы: мы обрабатываем их сами."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = build_opener(_NoRedirect)


def _check_address(url: str) -> None:
    """Пускаем только внешние адреса по http/https."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise FetchError('Ссылка должна начинаться с http:// или https://')

    host = parsed.hostname
    if not host:
        raise FetchError('В ссылке не указан адрес сайта.')

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise FetchError(f'Не удалось определить адрес сайта «{host}».') from None

    for info in addresses:
        ip = ipaddress.ip_address(info[4][0])
        # is_global отсекает разом: localhost, 192.168.*, 10.*, 169.254.*
        # (служебный адрес облаков) и прочие внутренние диапазоны.
        if not ip.is_global:
            raise FetchError('Ссылка ведёт на внутренний адрес — так нельзя.')


# Content-Disposition часто содержит ОБА варианта имени сразу:
#     attachment; filename="book.epub"; filename*=UTF-8''%D0%9C%D0%B5...
# Второй записан по RFC 5987, с явной кодировкой, и для нелатинских имён
# он точнее. Наивный split('filename=')[-1] хватал как раз служебный хвост
# второго варианта и склеивал из него мусор.
DISPOSITION_ENCODED = re.compile(r"filename\*\s*=\s*[\w-]+''([^;]+)", re.I)
DISPOSITION_PLAIN = re.compile(r'filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)', re.I)

# Символы, недопустимые в именах файлов Windows и Linux
UNSAFE_IN_NAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def _clean_name(raw: str) -> str:
    """Приводит имя к безопасному виду.

    Path(...).name отсекает каталоги: без этого имя вида «../../secret.epub»
    из чужого заголовка увело бы запись файла за пределы папки media.
    """
    name = UNSAFE_IN_NAME.sub('_', unquote(raw).strip().strip('"\' '))
    return Path(name).name[:120]


def _guess_name(url: str, content_type: str, disposition: str) -> str:
    """Определяем имя файла: из заголовка, из адреса или по типу содержимого."""
    for pattern in (DISPOSITION_ENCODED, DISPOSITION_PLAIN):
        found = pattern.search(disposition or '')
        if not found:
            continue
        candidate = _clean_name(next(g for g in found.groups() if g))
        if Path(candidate).suffix:
            return candidate

    name = _clean_name(Path(unquote(urlparse(url).path)).name)
    if Path(name).suffix:
        return name

    suffix = CONTENT_TYPES.get(content_type.split(';')[0].strip().lower(), '')
    return f'book{suffix}' if suffix else 'book'


def _read_limited(response) -> bytes:
    """Читаем с ограничением: без него ссылка на терабайт положила бы сервер."""
    data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FetchError(f'Файл больше {MAX_BYTES // 1024 // 1024} МБ.')
    if not data:
        raise FetchError('По ссылке пустой ответ.')
    return data


def fetch(url: str) -> tuple[bytes, str]:
    """Скачивает файл по ссылке. Возвращает (содержимое, имя файла)."""
    url = (url or '').strip()

    for _ in range(MAX_REDIRECTS):
        _check_address(url)                    # проверяем КАЖДЫЙ переход

        request = Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with _opener.open(request, timeout=TIMEOUT) as response:
                data = _read_limited(response)
                name = _guess_name(
                    url,
                    response.headers.get('Content-Type', ''),
                    response.headers.get('Content-Disposition', ''),
                )
                return data, name

        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                location = error.headers.get('Location', '')
                if not location:
                    raise FetchError('Сайт перенаправил в никуда.') from None
                url = urljoin(url, location)
                continue
            raise FetchError(f'Сайт ответил ошибкой {error.code}.') from None

        except URLError as error:
            raise FetchError(f'Не удалось связаться с сайтом: {error.reason}') from None
        except TimeoutError:
            raise FetchError('Сайт слишком долго не отвечает.') from None

    raise FetchError('Слишком много перенаправлений.')
