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

# ── Normalização de números por extenso ───────────────────────────────────────

_NUM_MAP = {
    'zero': 0, 'um': 1, 'uma': 1, 'dois': 2, 'duas': 2,
    'três': 3, 'tres': 3, 'quatro': 4, 'cinco': 5, 'seis': 6,
    'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10, 'onze': 11,
    'doze': 12, 'treze': 13, 'quatorze': 14, 'catorze': 14,
    'quinze': 15, 'dezesseis': 16, 'dezessete': 17, 'dezoito': 18,
    'dezenove': 19, 'vinte': 20, 'trinta': 30, 'quarenta': 40,
    'cinquenta': 50, 'sessenta': 60, 'setenta': 70, 'oitenta': 80,
    'noventa': 90, 'cem': 100, 'cento': 100, 'duzentos': 200,
    'duzentas': 200, 'trezentos': 300, 'trezentas': 300,
    'quatrocentos': 400, 'quatrocentas': 400, 'quinhentos': 500,
    'quinhentas': 500, 'seiscentos': 600, 'seiscentas': 600,
    'setecentos': 700, 'setecentas': 700, 'oitocentos': 800,
    'oitocentas': 800, 'novecentos': 900, 'novecentas': 900,
}

_NUM_WORDS_RE_STR = '|'.join(re.escape(w) for w in sorted(_NUM_MAP, key=len, reverse=True))
_NUM_SEQ_RE = re.compile(
    rf'\b(?:{_NUM_WORDS_RE_STR})(?:\s+e\s+(?:{_NUM_WORDS_RE_STR}))*\b',
    re.I | re.UNICODE,
)
_INNER_NUM_RE = re.compile(rf'\b({_NUM_WORDS_RE_STR})\b', re.I | re.UNICODE)


def _normalize_number_words(text: str) -> str:
    """Converte números por extenso para dígitos: 'vinte e dois' → '22', 'dois mil' → '2000'."""
    def _replace(m: re.Match) -> str:
        words = [_NUM_MAP[w.lower()] for w in _INNER_NUM_RE.findall(m.group(0))]
        return str(sum(words))

    text = _NUM_SEQ_RE.sub(_replace, text)
    text = re.sub(r'\b(\d+)\s+mil\s+e\s+(\d+)\b',
                  lambda m: str(int(m.group(1)) * 1000 + int(m.group(2))), text, flags=re.I)
    text = re.sub(r'\b(\d+)\s+mil\b',
                  lambda m: str(int(m.group(1)) * 1000), text, flags=re.I)
    text = re.sub(r'\bmil\b', '1000', text, flags=re.I)
    return text


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
    (re.compile(r'\bdia\s+(\d{1,2})-(\d{1,2})\b', re.I),           'dia_data_traco'),
    (re.compile(r'\b(\d{1,2}/\d{1,2})\b'),                          'data_curta'),
    (re.compile(r'\bdia\s+(\d{1,2})\b', re.I),                      'dia_numero'),
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

        if kind == 'dia_data_traco':
            day, month = int(m.group(1)), int(m.group(2))
            try:
                return now.replace(day=day, month=month), cleaned
            except ValueError:
                return now, cleaned

        if kind == 'dia_numero':
            try:
                return now.replace(day=int(m.group(1))), cleaned
            except ValueError:
                return now, cleaned

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
    normalized = _normalize_number_words(raw)

    value, after_value = _extract_value(normalized)
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
