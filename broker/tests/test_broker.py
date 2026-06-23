import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import fakeredis
import broker
import banco_redis as br
import banco_postgres as bp


# ------------------------------------------------------------------ #
#  Fixtures                                                           #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def setup_globals():
    broker._r  = fakeredis.FakeRedis(decode_responses=True)
    broker._pg = MagicMock()
    broker._pg_lock = MagicMock()
    broker._pg_lock.__enter__ = MagicMock(return_value=None)
    broker._pg_lock.__exit__  = MagicMock(return_value=False)
    yield


def _mock_conn():
    conn = MagicMock()
    conn.sendall = MagicMock()
    return conn


def _msg_enviada(conn):
    """Decodifica a última mensagem enviada ao conn."""
    data = conn.sendall.call_args[0][0].decode()
    return json.loads(data.strip())


def _todas_msgs(conn):
    """Decodifica todas as mensagens enviadas ao conn."""
    return [
        json.loads(c[0][0].decode().strip())
        for c in conn.sendall.call_args_list
    ]


# ------------------------------------------------------------------ #
#  _enviar                                                            #
# ------------------------------------------------------------------ #

class TestEnviar:
    def test_envia_json_com_newline(self):
        conn = _mock_conn()
        broker._enviar(conn, {'tipo': 'ok'})
        data = conn.sendall.call_args[0][0].decode()
        assert data.endswith('\n')
        assert json.loads(data.strip()) == {'tipo': 'ok'}

    def test_nao_lanca_em_conn_fechada(self):
        conn = _mock_conn()
        conn.sendall.side_effect = OSError()
        broker._enviar(conn, {'tipo': 'ok'})  # não deve lançar


# ------------------------------------------------------------------ #
#  _handle_registro                                                   #
# ------------------------------------------------------------------ #

class TestHandleRegistro:
    def test_registro_bem_sucedido(self):
        conn = _mock_conn()
        with patch('banco_postgres.registrar_usuario', return_value=True):
            broker._handle_registro({'nome': 'Ana', 'senha': '123'}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'ok'

    def test_nome_duplicado(self):
        conn = _mock_conn()
        with patch('banco_postgres.registrar_usuario', return_value=False):
            broker._handle_registro({'nome': 'Ana', 'senha': '123'}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'erro'
        assert 'já existe' in msg['mensagem']

    def test_nome_vazio(self):
        conn = _mock_conn()
        broker._handle_registro({'nome': '', 'senha': '123'}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'erro'

    def test_senha_vazia(self):
        conn = _mock_conn()
        broker._handle_registro({'nome': 'Ana', 'senha': ''}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'erro'

    def test_nome_muito_longo(self):
        conn = _mock_conn()
        broker._handle_registro({'nome': 'A' * 51, 'senha': '123'}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'erro'
        assert 'longo' in msg['mensagem']

    def test_retorna_none(self):
        conn = _mock_conn()
        with patch('banco_postgres.registrar_usuario', return_value=True):
            resultado = broker._handle_registro({'nome': 'Ana', 'senha': '123'}, conn)
        assert resultado is None


# ------------------------------------------------------------------ #
#  _handle_login                                                      #
# ------------------------------------------------------------------ #

class TestHandleLogin:
    def test_login_bem_sucedido(self):
        conn = _mock_conn()
        with patch('banco_postgres.autenticar', return_value=True):
            resultado = broker._handle_login({'nome': 'Ana', 'senha': '123'}, conn)
        assert resultado is not None
        nome, token = resultado
        assert nome == 'Ana'
        assert len(token) == 32  # uuid4 hex

    def test_credenciais_invalidas(self):
        conn = _mock_conn()
        with patch('banco_postgres.autenticar', return_value=False):
            resultado = broker._handle_login({'nome': 'Ana', 'senha': 'errada'}, conn)
        assert resultado is None
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'erro'

    def test_token_enviado_ao_cliente(self):
        conn = _mock_conn()
        with patch('banco_postgres.autenticar', return_value=True):
            resultado = broker._handle_login({'nome': 'Ana', 'senha': '123'}, conn)
        msg = _msg_enviada(conn)
        assert msg['tipo'] == 'ok'
        assert 'token' in msg

    def test_sessao_salva_no_redis(self):
        conn = _mock_conn()
        with patch('banco_postgres.autenticar', return_value=True):
            resultado = broker._handle_login({'nome': 'Ana', 'senha': '123'}, conn)
        nome, token = resultado
        assert br.sessao_existe(broker._r, token)

    def test_sessao_anterior_removida(self):
        conn = _mock_conn()
        # Salva sessão antiga
        br.salvar_sessao(broker._r, 'token_velho', 'Ana')
        with patch('banco_postgres.autenticar', return_value=True):
            broker._handle_login({'nome': 'Ana', 'senha': '123'}, conn)
        # Token velho deve ter sido removido
        assert not br.sessao_existe(broker._r, 'token_velho')

    def test_nome_vazio(self):
        conn = _mock_conn()
        resultado = broker._handle_login({'nome': '', 'senha': '123'}, conn)
        assert resultado is None

    def test_senha_vazia(self):
        conn = _mock_conn()
        resultado = broker._handle_login({'nome': 'Ana', 'senha': ''}, conn)
        assert resultado is None


# ------------------------------------------------------------------ #
#  banco_redis (módulo do broker)                                     #
# ------------------------------------------------------------------ #

class TestBancoRedisBroker:
    @pytest.fixture
    def r(self):
        return fakeredis.FakeRedis(decode_responses=True)

    def test_salvar_e_obter_sessao(self, r):
        br.salvar_sessao(r, 'tok1', 'Ana')
        sessao = br.obter_sessao(r, 'tok1')
        assert sessao['nome'] == 'Ana'

    def test_sessao_existe(self, r):
        br.salvar_sessao(r, 'tok1', 'Ana')
        assert br.sessao_existe(r, 'tok1') is True
        assert br.sessao_existe(r, 'outro') is False

    def test_token_por_nome(self, r):
        br.salvar_sessao(r, 'tok1', 'Ana')
        assert br.token_por_nome(r, 'Ana') == 'tok1'

    def test_remover_sessao(self, r):
        br.salvar_sessao(r, 'tok1', 'Ana')
        br.remover_sessao(r, 'tok1', 'Ana')
        assert br.sessao_existe(r, 'tok1') is False
        assert br.token_por_nome(r, 'Ana') is None

    def test_atualizar_sala(self, r):
        br.salvar_sessao(r, 'tok1', 'Ana')
        br.atualizar_sessao_sala(r, 'tok1', 5)
        sessao = br.obter_sessao(r, 'tok1')
        assert sessao['sala'] == '5'

    def test_sessao_inexistente_retorna_none(self, r):
        assert br.obter_sessao(r, 'naoexiste') is None


# ------------------------------------------------------------------ #
#  banco_postgres (módulo do broker)                                  #
# ------------------------------------------------------------------ #

class TestBancoPostgresBroker:
    @pytest.fixture
    def conn(self):
        mock_conn = MagicMock()
        mock_cur  = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.cursor.return_value.__exit__.return_value = False
        return mock_conn, mock_cur

    def test_registrar_usuario_ok(self, conn):
        mock_conn, _ = conn
        resultado = bp.registrar_usuario(mock_conn, 'Ana', 'senha')
        assert resultado is True

    def test_registrar_usuario_duplicado(self, conn):
        import psycopg2
        mock_conn, mock_cur = conn
        mock_cur.execute.side_effect = psycopg2.IntegrityError()
        resultado = bp.registrar_usuario(mock_conn, 'Ana', 'senha')
        assert resultado is False
        mock_conn.rollback.assert_called_once()

    def test_autenticar_ok(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        assert bp.autenticar(mock_conn, 'Ana', 'senha') is True

    def test_autenticar_falha(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        assert bp.autenticar(mock_conn, 'Ana', 'errada') is False

    def test_usuario_existe(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        assert bp.usuario_existe(mock_conn, 'Ana') is True

    def test_usuario_nao_existe(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        assert bp.usuario_existe(mock_conn, 'Ana') is False

    def test_senha_salva_com_hash(self, conn):
        mock_conn, mock_cur = conn
        bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        _, params = mock_cur.execute.call_args.args
        assert params[1] == bp.hash_senha('senha123')
        assert 'senha123' not in params[1]
