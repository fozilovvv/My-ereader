"""Компилирует переводы .po в бинарные .mo — без внешнего gettext.

Обычно это делает `django manage.py compilemessages`, но она требует
установленной утилиты msgfmt из GNU gettext, которой на Windows почти
никогда нет. Формат .mo при этом простой и описан в документации gettext,
поэтому проще собрать его самим, чем тянуть в проект целый пакет утилит.

    python manage.py compilepo
"""
import array
import struct
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

MAGIC = 0x950412DE      # подпись формата .mo, порядок байтов — little-endian


def parse_po(text: str) -> dict:
    """Читает .po в словарь {оригинал: перевод}.

    Понимает многострочные записи: msgid "" с продолжением на следующих
    строках — так gettext переносит длинные фразы.
    """
    entries = {}
    key = value = None
    target = None           # куда сейчас копим строки: 'id' или 'str'

    def flush():
        if key is not None and value:
            entries[key] = value

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        if line.startswith('msgid '):
            flush()
            key, value, target = _unquote(line[6:]), '', 'id'
        elif line.startswith('msgstr '):
            value, target = _unquote(line[7:]), 'str'
        elif line.startswith('"') and target:
            chunk = _unquote(line)
            if target == 'id':
                key += chunk
            else:
                value += chunk

    flush()
    return entries


def _unquote(raw: str) -> str:
    """Снимает кавычки и разворачивает экранированные символы."""
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    return raw.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')


def build_mo(entries: dict) -> bytes:
    """Собирает бинарный .mo из пар «оригинал → перевод»."""
    # Пустой msgid — служебная запись с метаданными каталога, она нужна
    # gettext, и по соглашению идёт первой. Сортировка обязательна:
    # читатели .mo рассчитывают на упорядоченную таблицу.
    items = sorted(entries.items())

    ids = b''
    strs = b''
    offsets = []
    for original, translated in items:
        source = original.encode('utf-8')
        target = translated.encode('utf-8')
        offsets.append((len(ids), len(source), len(strs), len(target)))
        ids += source + b'\x00'
        strs += target + b'\x00'

    count = len(items)
    keystart = 7 * 4 + 16 * count          # заголовок + две таблицы по 8 байт на запись
    valuestart = keystart + len(ids)

    koffsets = []
    voffsets = []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]

    output = struct.pack(
        '<7I',
        MAGIC,          # подпись
        0,              # версия формата
        count,          # сколько строк
        7 * 4,          # где начинается таблица оригиналов
        7 * 4 + count * 8,   # где начинается таблица переводов
        0, 0,           # хеш-таблица не используется
    )
    output += array.array('i', koffsets + voffsets).tobytes()
    return output + ids + strs


class Command(BaseCommand):
    help = 'Собирает .mo из .po без установленного gettext'

    def handle(self, *args, **options):
        roots = [Path(path) for path in settings.LOCALE_PATHS]
        found = 0

        for root in roots:
            for po_path in sorted(root.glob('*/LC_MESSAGES/*.po')):
                entries = parse_po(po_path.read_text(encoding='utf-8'))
                mo_path = po_path.with_suffix('.mo')
                mo_path.write_bytes(build_mo(entries))
                found += 1
                self.stdout.write(
                    f'  {po_path.parent.parent.name}: строк {len(entries):>4} -> {mo_path.name}'
                )

        if not found:
            self.stdout.write(self.style.WARNING('Файлы .po не найдены.'))
            return
        self.stdout.write(self.style.SUCCESS(f'Готово. Каталогов собрано: {found}.'))
