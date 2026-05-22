import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

import dateparser

_TZ = ZoneInfo("America/Sao_Paulo")


@dataclass
class Expense:
    value: float
    description: str
    date: str        # DD/MM/YYYY
    time: str        # HH:MM
    raw_message: str


# ── Extração de valor ─────────────────────────────────────────────────────────
# Ordenado do mais específico ao mais genérico para evitar falsos positivos.
# Suporta formato brasileiro (ponto = milhar, vírgula = decimal).

_VALUE_PATTERNS = [
    re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', re.I),    # R$ 1.500,00
    re.compile(r'R\$\s*(\d+,\d{2})', re.I),                     # R$ 150,50
    re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})+)', re.I),           # R$ 1.500
    re.compile(r'R\$\s*(\d+)', re.I),                            # R$ 150
    re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})\s*reais?', re.I),  # 1.500,00 reais
    re.compile(r'(\d+,\d{2})\s*reais?', re.I),                   # 150,50 reais
    re.compile(r'(\d{1,3}(?:\.\d{3})+)\s*reais?', re.I),        # 1.500 reais
    re.compile(r'(\d+)\s*reais?', re.I),                         # 150 reais
    re.compile(r'(\d{1,3}(?:\.\d{3})*,\d{2})', re.I),           # 1.500,00
    re.compile(r'(\d+,\d{2})', re.I),                            # 150,50
    re.compile(r'(\d{1,3}(?:\.\d{3})+)', re.I),                  # 1.500
    re.compile(r'(?<![/\d])(\d+)(?![/:\d])', re.I),              # 150 (último recurso, evita datas)
]


def _to_float(raw: str) -> float:
    raw = re.sub(r'^R\$\s*', '', raw.strip())
    if ',' in raw and '.' in raw:
        return float(raw.replace('.', '').replace(',', '.'))
    if ',' in raw:
        return float(raw.replace(',', '.'))
    if re.search(r'\.\d{3}$', raw):
        return float(raw.replace('.', ''))
    return float(raw)


def _extract_value(text: str) -> Tuple[Optional[float], str]:
    for pattern in _VALUE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            value = _to_float(m.group(1))
            cleaned = (text[:m.start()] + text[m.end():]).strip()
            return value, cleaned
        except ValueError:
            continue
    return None, text


# ── Extração de data e hora ───────────────────────────────────────────────────

_DATE_PATTERNS = [
    (re.compile(r'\b(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2})\b'), 'data_hora_completa'),
    (re.compile(r'\b(\d{1,2}/\d{1,2}/\d{4})\b'),                    'data_completa'),
    (re.compile(r'\bdia\s+(\d{1,2}/\d{1,2}/\d{2,4})\b', re.I),     'dia_data_completa'),
    (re.compile(r'\b(\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})\b'),       'data_curta_hora'),
    (re.compile(r'\bdia\s+(\d{1,2}/\d{1,2})\b', re.I),              'dia_data_curta'),
    (re.compile(r'\b(\d{1,2}/\d{1,2})\b'),                          'data_curta'),
    (re.compile(r'\b(anteontem)\b', re.I),                           'relativa'),
    (re.compile(r'\b(ontem)\b', re.I),                               'relativa'),
    (re.compile(r'\b(hoje)\b', re.I),                                'relativa'),
    (re.compile(r'\b(\d{1,2}:\d{2})\b'),                             'hora'),
]

_DELTA_RELATIVO = {'hoje': 0, 'ontem': -1, 'anteontem': -2}


def _extract_datetime(text: str) -> Tuple[datetime, str]:
    now = datetime.now(tz=_TZ).replace(second=0, microsecond=0)

    for pattern, kind in _DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue

        cleaned = (text[:m.start()] + text[m.end():]).strip()

        if kind == 'relativa':
            delta = _DELTA_RELATIVO[m.group(1).lower()]
            return now + timedelta(days=delta), cleaned

        if kind == 'hora':
            h, mi = map(int, m.group(1).split(':'))
            return now.replace(hour=h, minute=mi), cleaned

        if kind == 'data_hora_completa':
            date_str = f"{m.group(1)} {m.group(2)}"
            parsed = dateparser.parse(date_str, languages=['pt'],
                                      settings={'DATE_ORDER': 'DMY'})
            return (parsed if parsed else now), cleaned

        if kind == 'data_curta_hora':
            date_str = f"{m.group(1)}/{now.year} {m.group(2)}"
            parsed = dateparser.parse(date_str, languages=['pt'],
                                      settings={'DATE_ORDER': 'DMY'})
            return (parsed if parsed else now), cleaned

        # Apenas data (sem hora) → mantém hora atual
        date_part = m.group(1)
        if kind in ('data_curta', 'dia_data_curta'):
            date_part = f"{date_part}/{now.year}"
        parsed = dateparser.parse(date_part, languages=['pt'],
                                  settings={'DATE_ORDER': 'DMY'})
        if parsed:
            return parsed.replace(hour=now.hour, minute=now.minute), cleaned

    return now, text


# ── API pública ───────────────────────────────────────────────────────────────

def parse_message(text: str) -> Optional[Expense]:
    """Extrai dados de gasto a partir de uma mensagem de texto."""
    if not text or not text.strip():
        return None

    raw = text.strip()

    value, after_value = _extract_value(raw)
    if value is None:
        return None

    dt, description = _extract_datetime(after_value)

    description = re.sub(r'[-–—]+', ' ', description)
    description = ' '.join(description.split()).strip('-–— .,;:')
    if not description:
        description = 'sem descrição'

    return Expense(
        value=value,
        description=description,
        date=dt.strftime('%d/%m/%Y'),
        time=dt.strftime('%H:%M'),
        raw_message=raw,
    )
