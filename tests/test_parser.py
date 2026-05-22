from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.parser import Expense, parse_message

_NOW = datetime(2026, 5, 21, 14, 30)
_TODAY = _NOW.strftime('%d/%m/%Y')
_YESTERDAY = (_NOW - timedelta(days=1)).strftime('%d/%m/%Y')
_DAY_BEFORE = (_NOW - timedelta(days=2)).strftime('%d/%m/%Y')


@pytest.fixture(autouse=True)
def fixed_now():
    with patch('app.parser.datetime') as mock_dt:
        mock_dt.now.return_value = _NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        yield


# ── Valor ─────────────────────────────────────────────────────────────────────

class TestValor:
    def test_inteiro_com_reais(self):
        assert parse_message('gasolina 150 reais').value == 150.0

    def test_r_cifrao_simples(self):
        assert parse_message('troca de oleo R$ 280').value == 280.0

    def test_decimal_virgula(self):
        assert parse_message('combustivel 200,50').value == 200.50

    def test_decimal_com_reais(self):
        assert parse_message('lavagem 49,90 reais').value == 49.90

    def test_milhar_ponto(self):
        assert parse_message('seguro 1.500 reais').value == 1500.0

    def test_formato_br_completo(self):
        assert parse_message('seguro R$ 1.500,00').value == 1500.0

    def test_valor_antes_descricao(self):
        e = parse_message('R$ 350 documentacao carro')
        assert e.value == 350.0
        assert 'documentacao' in e.description

    def test_valor_no_meio(self):
        e = parse_message('oleo 180 reais ontem')
        assert e.value == 180.0


# ── Data ──────────────────────────────────────────────────────────────────────

class TestData:
    def test_sem_data_usa_hoje(self):
        assert parse_message('gasolina 150 reais').date == _TODAY

    def test_ontem(self):
        assert parse_message('lavagem 50 ontem').date == _YESTERDAY

    def test_anteontem(self):
        assert parse_message('multa 200 anteontem').date == _DAY_BEFORE

    def test_hoje_explicito(self):
        assert parse_message('gasolina 150 hoje').date == _TODAY

    def test_data_completa(self):
        assert parse_message('IPVA 800 reais 15/03/2026').date == '15/03/2026'

    def test_data_completa_com_hora(self):
        e = parse_message('IPVA 800 reais 15/03/2026 09:30')
        assert e.date == '15/03/2026'
        assert e.time == '09:30'

    def test_data_curta(self):
        e = parse_message('multa 200 10/05')
        assert e.date == f'10/05/{_NOW.year}'

    def test_dia_prefix(self):
        e = parse_message('troca de oleo R$ 280 dia 10/05')
        assert e.date == f'10/05/{_NOW.year}'

    def test_hora_sem_data_mantem_hoje(self):
        e = parse_message('gasolina 150 09:00')
        assert e.date == _TODAY
        assert e.time == '09:00'


# ── Descrição ─────────────────────────────────────────────────────────────────

class TestDescricao:
    def test_descricao_antes_do_valor(self):
        assert parse_message('gasolina 150 reais').description == 'gasolina'

    def test_descricao_depois_do_valor(self):
        assert parse_message('R$ 350 documentacao carro').description == 'documentacao carro'

    def test_sem_descricao(self):
        assert parse_message('150 reais').description == 'sem descrição'

    def test_descricao_maiuscula(self):
        assert parse_message('GASOLINA 150 REAIS').description == 'GASOLINA'

    def test_descricao_com_traco(self):
        e = parse_message('Gasolina - 180 reais - ontem')
        assert e.description == 'Gasolina'

    def test_mensagem_original_preservada(self):
        msg = 'IPVA 800 reais 15/03/2026 09:30'
        assert parse_message(msg).raw_message == msg


# ── Casos extremos ────────────────────────────────────────────────────────────

class TestCasosExtremos:
    def test_string_vazia(self):
        assert parse_message('') is None

    def test_apenas_espacos(self):
        assert parse_message('   ') is None

    def test_sem_valor_retorna_none(self):
        assert parse_message('gasolina ontem') is None

    def test_descricao_multiplas_palavras(self):
        e = parse_message('troca de oleo e filtro 320 reais')
        assert e.value == 320.0
        assert 'troca' in e.description
