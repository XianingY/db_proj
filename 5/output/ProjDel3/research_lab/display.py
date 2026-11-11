"""Pure terminal formatting helpers shared by the CLI and the web layer.

These functions have no database or menu state, so the layout rules can be
tested on their own. cli.py re-exports every name here, keeping the existing
``from research_lab.cli import ...`` imports valid.
"""
import json
import shutil
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .service import TABLES


LABELS = {key: value.split('|')[0] for _, _, fields in TABLES.values()
          for key, value in fields.items()}
LABELS.update(title='标题', full_name='姓名', status='状态', leader_name='负责人姓名',
    total_funding_usd='总资助 USD', mentor_id='导师编号', mentor_name='导师姓名',
    mentee_id='被指导者编号', mentee_name='被指导者姓名', publication_count='成果数',
    grant_count='资助数', device_count='装置数', available_device_count='可用数',
    in_use_device_count='使用中数', retired_device_count='退役数', devices='装置明细',
    mentorship_start_date='指导开始日', mentorship_end_date='指导结束日')


def parse_value(value, field_type='str'):
    nullable = field_type.endswith('?')
    kind = field_type.rstrip('?')
    if value.upper() == 'NULL' or not value:
        if nullable:
            return None
        raise ValueError('此字段不能为空')
    try:
        if kind == 'date':
            return date.fromisoformat(value)
        if kind == 'datetime':
            result = datetime.fromisoformat(value)
            if result.tzinfo is not None or result.microsecond:
                raise ValueError('使用时刻须为北京时间、精确到秒，不附时区或小数秒')
            return result
        if kind == 'int':
            return int(value)
        if kind == 'decimal':
            result = Decimal(value)
            if not result.is_finite():
                raise ValueError('数值必须有限，不能为 NaN 或 Infinity')
            return result
        return value
    except (ValueError, InvalidOperation) as error:
        raise ValueError(f'无效 {kind} 输入：{value}；{error}') from error


def pretty(value):
    if value is None:
        return 'NULL'
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value, (dict,list)):
        return json.dumps(value,ensure_ascii=False,default=str)
    return str(value).replace('\n',' ')


# A column never gets narrower than this, so IDs and dates stay legible.
MIN_COLUMN_WIDTH = 5
# Header text may wrap, but only after every column already has room for its data.
HEADER_WIDTH_CAP = 12
# Short ASCII values (timestamps, enums) are kept whole instead of split at spaces.
HARD_TOKEN_LIMIT = 24


def width(value):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in value)


def tokens(value):
    """Split into unbreakable units: CJK characters break freely, ASCII runs do not.

    Keeps `2020-09-01` and `collaborator` on one line instead of splitting them
    mid-token, which is what makes a narrow terminal table still readable.
    """
    units, buffer = [], ''
    for character in value:
        if unicodedata.east_asian_width(character) in 'WF':
            if buffer:
                units.append(buffer)
                buffer = ''
            units.append(character)
        elif character == ' ':
            if buffer:
                units.append(buffer)
                buffer = ''
            units.append(' ')
        else:
            buffer += character
    if buffer:
        units.append(buffer)
    return units or ['']


def minimum_width(value):
    """Narrowest width that still avoids breaking an indivisible token.

    A short pure-ASCII value such as `2024-01-15 09:00:00` is one token, so the
    timestamp column never wraps mid-value; CJK text may still break anywhere.
    """
    if width(value) <= HARD_TOKEN_LIMIT and not any(
            unicodedata.east_asian_width(c) in 'WF' for c in value):
        return width(value)
    return max((width(unit) for unit in tokens(value) if unit.strip()), default=1)


def wrapped(value, maximum):
    lines, line = [], ''
    for unit in tokens(value):
        if line and width(line + unit) > maximum:
            lines.append(line.rstrip())
            line = '' if unit == ' ' else unit
        else:
            line += unit
        while width(line) > maximum:  # a single token longer than the column
            cut = len(line)
            while cut > 1 and width(line[:cut]) > maximum:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    return lines + [line.rstrip()]


def fit_sizes(natural, minimum, budget):
    """Give every column its minimum, then spend the rest on the largest deficits."""
    sizes = [min(n, m) if n < m else m for n, m in zip(natural, minimum)]
    remaining = budget - sum(sizes)
    while remaining > 0:
        deficits = [(natural[i] - sizes[i], -i) for i in range(len(sizes))]
        largest = max(deficits)
        if largest[0] <= 0:
            break
        index = -largest[1]
        sizes[index] += 1
        remaining -= 1
    return sizes


def table_lines(headers, cells, sizes):
    def render(line):
        return ' | '.join(value + ' ' * (sizes[i] - width(value)) for i, value in enumerate(line))
    lines = [render([wrapped(h, sizes[i])[0] for i, h in enumerate(headers)]),
             '-+-'.join('-' * n for n in sizes)]
    header_fragments = [wrapped(h, sizes[i]) for i, h in enumerate(headers)]
    if any(len(f) > 1 for f in header_fragments):
        lines = []
        for depth in range(max(map(len, header_fragments))):
            lines.append(render([f[depth] if depth < len(f) else '' for f in header_fragments]))
        lines.append('-+-'.join('-' * n for n in sizes))
    for row in cells:
        # Wrap instead of truncating: no value is ever silently cut off.
        fragments = [wrapped(value, sizes[i]) for i, value in enumerate(row)]
        for depth in range(max(map(len, fragments))):
            lines.append(render([part[depth] if depth < len(part) else '' for part in fragments]))
    return lines


def record_lines(rows, columns):
    lines = []
    for index, row in enumerate(rows, 1):
        lines.append(f'── 记录 {index} ──')
        for key in columns:
            lines.append(f'  {LABELS.get(key, key)}: {pretty(row[key])}')
    return lines


def emit(lines):
    """Page long output on a real terminal only; pipes and logs get everything."""
    if not sys.stdout.isatty():
        print('\n'.join(lines))
        return
    page = max(8, shutil.get_terminal_size((100, 24)).lines - 3)
    for start in range(0, len(lines), page):
        print('\n'.join(lines[start:start + page]))
        remaining = len(lines) - start - page
        if remaining <= 0:
            return
        try:
            answer = input(f'── 还有 {remaining} 行，回车继续 / q 回车跳过 ── ')
        except EOFError:
            return
        if answer.strip().lower() == 'q':
            return


def display_rows(rows):
    """Print rows as a table when the terminal is wide enough, else per record.

    Widths follow the live terminal, so a nine-column report stays a table
    instead of turning into one vertical block per row.
    """
    if not rows:
        print('无匹配记录。')
        return
    columns = list(rows[0])
    headers = [LABELS.get(key, key) for key in columns]
    cells = [[pretty(row[key]) for key in columns] for row in rows]
    available = max(40, shutil.get_terminal_size((100, 24)).columns - 2)
    natural = [max(width(headers[i]), *(width(row[i]) for row in cells))
               for i in range(len(columns))]
    data_floor = [max(MIN_COLUMN_WIDTH,
                      minimum_width(headers[i]),
                      *(minimum_width(row[i]) for row in cells)) for i in range(len(columns))]
    # First try to keep every header on one line; only if that cannot fit do we
    # let headers wrap, and only as a last resort fall back to one block per row.
    header_floor = [max(floor, min(width(headers[i]), HEADER_WIDTH_CAP))
                    for i, floor in enumerate(data_floor)]
    separators = 3 * (len(columns) - 1)
    budget = available - separators
    for floor in (header_floor, data_floor):
        if sum(max(f, m) for f, m in zip(floor, data_floor)) > budget:
            continue
        sizes = fit_sizes(natural, [max(f, m) for f, m in zip(floor, data_floor)], budget)
        if sum(sizes) + separators <= available:
            emit(table_lines(headers, cells, sizes))
            break
    else:
        emit(record_lines(rows, columns))
    print(f'共 {len(rows)} 条记录。')
