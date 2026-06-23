import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import psycopg2
import banco_postgres as bp


# ------------------------------------------------------------------ #
#  Fixture: conexão mockada                                           #
# ------------------------------------------------------------------ #

@pytest.fixture
def conn():
    """Mock de conexão psycopg2 com cursor como context manager."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value.__exit__.return_value = False
    return mock_conn, mock_cur


# ------------------------------------------------------------------ #
#  hash_senha                                                         #
# ------------------------------------------------------------------ #

class TestHashSenha:
    def test_retorna_string_64_chars(self):
        h = bp.hash_senha('minhasenha')
        assert isinstance(h, str)
        assert len(h) == 64

    def test_deterministico(self):
        assert bp.hash_senha('abc') == bp.hash_senha('abc')

    def test_senhas_diferentes_hash_diferente(self):
        assert bp.hash_senha('abc') != bp.hash_senha('def')

    def test_nao_armazena_senha_em_claro(self):
        assert 'minhasenha' not in bp.hash_senha('minhasenha')


# ------------------------------------------------------------------ #
#  criar_tabelas                                                      #
# ------------------------------------------------------------------ #

class TestCriarTabelas:
    def test_executa_dois_creates(self, conn):
        mock_conn, mock_cur = conn
        bp.criar_tabelas(mock_conn)
        assert mock_cur.execute.call_count == 2
        mock_conn.commit.assert_called_once()

    def test_cria_tabela_usuarios(self, conn):
        mock_conn, mock_cur = conn
        bp.criar_tabelas(mock_conn)
        sql_calls = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any('usuarios' in sql for sql in sql_calls)

    def test_cria_tabela_partidas(self, conn):
        mock_conn, mock_cur = conn
        bp.criar_tabelas(mock_conn)
        sql_calls = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any('partidas' in sql for sql in sql_calls)


# ------------------------------------------------------------------ #
#  registrar_usuario                                                  #
# ------------------------------------------------------------------ #

class TestRegistrarUsuario:
    def test_insert_executado(self, conn):
        mock_conn, mock_cur = conn
        bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        mock_cur.execute.assert_called_once()
        sql, params = mock_cur.execute.call_args.args
        assert 'INSERT' in sql
        assert params[0] == 'Ana'
        assert params[1] == bp.hash_senha('senha123')

    def test_commit_apos_insert(self, conn):
        mock_conn, mock_cur = conn
        bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        mock_conn.commit.assert_called_once()

    def test_retorna_true_em_sucesso(self, conn):
        mock_conn, mock_cur = conn
        resultado = bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        assert resultado is True

    def test_retorna_false_se_nome_duplicado(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.execute.side_effect = psycopg2.IntegrityError()
        resultado = bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        assert resultado is False

    def test_rollback_em_duplicado(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.execute.side_effect = psycopg2.IntegrityError()
        bp.registrar_usuario(mock_conn, 'Ana', 'senha123')
        mock_conn.rollback.assert_called_once()


# ------------------------------------------------------------------ #
#  autenticar                                                         #
# ------------------------------------------------------------------ #

class TestAutenticar:
    def test_retorna_true_se_encontrou(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        assert bp.autenticar(mock_conn, 'Ana', 'senha123') is True

    def test_retorna_false_se_nao_encontrou(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        assert bp.autenticar(mock_conn, 'Ana', 'senhaerrada') is False

    def test_usa_hash_na_query(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        bp.autenticar(mock_conn, 'Ana', 'senha123')
        _, params = mock_cur.execute.call_args.args
        assert params[1] == bp.hash_senha('senha123')


# ------------------------------------------------------------------ #
#  usuario_existe                                                     #
# ------------------------------------------------------------------ #

class TestUsuarioExiste:
    def test_existe(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        assert bp.usuario_existe(mock_conn, 'Ana') is True

    def test_nao_existe(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        assert bp.usuario_existe(mock_conn, 'Ana') is False


# ------------------------------------------------------------------ #
#  obter_perfil                                                       #
# ------------------------------------------------------------------ #

class TestObterPerfil:
    def test_retorna_perfil_completo(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = ('Ana', 6, 10)
        perfil = bp.obter_perfil(mock_conn, 'Ana')
        assert perfil['nome'] == 'Ana'
        assert perfil['vitorias'] == 6
        assert perfil['partidas'] == 10
        assert perfil['derrotas'] == 4

    def test_derrotas_calculadas(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = ('Bob', 3, 8)
        perfil = bp.obter_perfil(mock_conn, 'Bob')
        assert perfil['derrotas'] == 5

    def test_retorna_none_se_nao_existe(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = None
        assert bp.obter_perfil(mock_conn, 'Ninguem') is None

    def test_derrotas_zero(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = ('Ana', 5, 5)
        perfil = bp.obter_perfil(mock_conn, 'Ana')
        assert perfil['derrotas'] == 0


# ------------------------------------------------------------------ #
#  obter_ranking                                                      #
# ------------------------------------------------------------------ #

class TestObterRanking:
    def test_retorna_lista_ordenada(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchall.return_value = [('Ana', 10), ('Bob', 7), ('Carlos', 3)]
        ranking = bp.obter_ranking(mock_conn)
        assert len(ranking) == 3
        assert ranking[0] == {'nome': 'Ana', 'vitorias': 10}
        assert ranking[1] == {'nome': 'Bob', 'vitorias': 7}

    def test_lista_vazia(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchall.return_value = []
        assert bp.obter_ranking(mock_conn) == []

    def test_limite_padrao_10(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchall.return_value = []
        bp.obter_ranking(mock_conn)
        _, params = mock_cur.execute.call_args.args
        assert params[0] == 10

    def test_limite_customizado(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchall.return_value = []
        bp.obter_ranking(mock_conn, limite=5)
        _, params = mock_cur.execute.call_args.args
        assert params[0] == 5


# ------------------------------------------------------------------ #
#  registrar_vitoria / registrar_derrota                              #
# ------------------------------------------------------------------ #

class TestRegistrarResultado:
    def test_vitoria_incrementa_vitorias_e_partidas(self, conn):
        mock_conn, mock_cur = conn
        bp.registrar_vitoria(mock_conn, 'Ana')
        sql, params = mock_cur.execute.call_args.args
        assert 'vitorias = vitorias + 1' in sql
        assert 'partidas = partidas + 1' in sql
        assert params[0] == 'Ana'
        mock_conn.commit.assert_called_once()

    def test_derrota_incrementa_so_partidas(self, conn):
        mock_conn, mock_cur = conn
        bp.registrar_derrota(mock_conn, 'Bob')
        sql, params = mock_cur.execute.call_args.args
        assert 'partidas = partidas + 1' in sql
        assert 'vitorias' not in sql
        assert params[0] == 'Bob'
        mock_conn.commit.assert_called_once()


# ------------------------------------------------------------------ #
#  total_usuarios                                                     #
# ------------------------------------------------------------------ #

class TestTotalUsuarios:
    def test_retorna_contagem(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (42,)
        assert bp.total_usuarios(mock_conn) == 42

    def test_retorna_zero_se_vazio(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (0,)
        assert bp.total_usuarios(mock_conn) == 0


# ------------------------------------------------------------------ #
#  iniciar_partida                                                    #
# ------------------------------------------------------------------ #

class TestIniciarPartida:
    def test_retorna_id(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (7,)
        partida_id = bp.iniciar_partida(mock_conn, sala_id=3, tipo='normal')
        assert partida_id == 7

    def test_insert_com_sala_e_tipo(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        bp.iniciar_partida(mock_conn, sala_id=5, tipo='1v1')
        sql, params = mock_cur.execute.call_args.args
        assert 'INSERT' in sql
        assert params == (5, '1v1')

    def test_commit_apos_insert(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (1,)
        bp.iniciar_partida(mock_conn, 1, 'normal')
        mock_conn.commit.assert_called_once()


# ------------------------------------------------------------------ #
#  encerrar_partida                                                   #
# ------------------------------------------------------------------ #

class TestEncerrarPartida:
    def test_update_executado(self, conn):
        mock_conn, mock_cur = conn
        bp.encerrar_partida(mock_conn, 7, ['Ana', 'Carlos'], ['Bob', 'Dani'], 'completa')
        sql, params = mock_cur.execute.call_args.args
        assert 'UPDATE' in sql
        assert 'encerrada_em' in sql

    def test_vencedores_em_string(self, conn):
        mock_conn, mock_cur = conn
        bp.encerrar_partida(mock_conn, 7, ['Ana', 'Carlos'], ['Bob', 'Dani'], 'completa')
        _, params = mock_cur.execute.call_args.args
        assert params[0] == 'Ana,Carlos'
        assert params[1] == 'Bob,Dani'

    def test_status_wo(self, conn):
        mock_conn, mock_cur = conn
        bp.encerrar_partida(mock_conn, 7, ['Ana'], ['Bob'], 'wo')
        _, params = mock_cur.execute.call_args.args
        assert params[2] == 'wo'

    def test_commit_apos_update(self, conn):
        mock_conn, mock_cur = conn
        bp.encerrar_partida(mock_conn, 7, ['Ana'], ['Bob'], 'completa')
        mock_conn.commit.assert_called_once()

    def test_listas_vazias_viram_string_vazia(self, conn):
        mock_conn, mock_cur = conn
        bp.encerrar_partida(mock_conn, 7, [], [], 'wo')
        _, params = mock_cur.execute.call_args.args
        assert params[0] == ''
        assert params[1] == ''


# ------------------------------------------------------------------ #
#  total_partidas                                                     #
# ------------------------------------------------------------------ #

class TestTotalPartidas:
    def test_retorna_contagem(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (15,)
        assert bp.total_partidas(mock_conn) == 15

    def test_conta_so_encerradas(self, conn):
        mock_conn, mock_cur = conn
        mock_cur.fetchone.return_value = (0,)
        bp.total_partidas(mock_conn)
        sql = mock_cur.execute.call_args.args[0]
        assert 'encerrada_em IS NOT NULL' in sql
