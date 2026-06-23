import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import servidor as srv
from jogo import Jogo


# ------------------------------------------------------------------ #
#  Fixtures                                                           #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def reset_salas():
    """Reinicia as salas antes de cada teste."""
    srv._salas.clear()
    srv._timers_turno.clear()
    srv._timers_desconexao.clear()
    srv._inicializar_salas()
    yield


def _mock_conn():
    conn = MagicMock()
    conn.sendall = MagicMock()
    return conn


def _jogo_normal():
    j = Jogo(sala_id=1, jogadores=['Ana', 'Bob', 'Carlos', 'Dani'], tipo='normal')
    j.iniciar_mao()
    return j


def _jogo_1v1():
    j = Jogo(sala_id=14, jogadores=['Ana', 'Bob'], tipo='1v1')
    j.iniciar_mao()
    return j


# ------------------------------------------------------------------ #
#  _sala_vazia                                                        #
# ------------------------------------------------------------------ #

class TestSalaVazia:
    def test_campos_presentes(self):
        sala = srv._sala_vazia('normal', 4)
        assert sala['tipo'] == 'normal'
        assert sala['max'] == 4
        assert sala['jogadores'] == []
        assert sala['conexoes'] == {}
        assert sala['jogo'] is None
        assert sala['status'] == 'aguardando'

    def test_1v1(self):
        sala = srv._sala_vazia('1v1', 2)
        assert sala['max'] == 2
        assert sala['tipo'] == '1v1'


# ------------------------------------------------------------------ #
#  _inicializar_salas                                                 #
# ------------------------------------------------------------------ #

class TestInicializarSalas:
    def test_16_salas_criadas(self):
        assert len(srv._salas) == 16

    def test_salas_1_a_13_normais(self):
        for i in range(1, 14):
            assert srv._salas[i]['tipo'] == 'normal'
            assert srv._salas[i]['max'] == 4

    def test_salas_14_a_16_sao_1v1(self):
        for i in range(14, 17):
            assert srv._salas[i]['tipo'] == '1v1'
            assert srv._salas[i]['max'] == 2


# ------------------------------------------------------------------ #
#  info_salas                                                         #
# ------------------------------------------------------------------ #

class TestInfoSalas:
    def test_retorna_16_salas(self):
        info = srv.info_salas()
        assert len(info) == 16

    def test_formato_correto(self):
        info = srv.info_salas()
        sala = next(s for s in info if s['id'] == 1)
        assert 'tipo' in sala
        assert 'jogadores' in sala
        assert 'max' in sala
        assert 'status' in sala

    def test_sala_normal_max_4(self):
        info = srv.info_salas()
        sala = next(s for s in info if s['id'] == 1)
        assert sala['max'] == 4

    def test_sala_1v1_max_2(self):
        info = srv.info_salas()
        sala = next(s for s in info if s['id'] == 14)
        assert sala['max'] == 2

    def test_contagem_jogadores(self):
        srv._salas[1]['jogadores'] = ['Ana', 'Bob']
        info = srv.info_salas()
        sala = next(s for s in info if s['id'] == 1)
        assert sala['jogadores'] == 2


# ------------------------------------------------------------------ #
#  montar_estado_para                                                 #
# ------------------------------------------------------------------ #

class TestMontarEstadoPara:
    def setup_method(self):
        self.jogo = _jogo_normal()
        srv._salas[1]['jogo'] = self.jogo
        srv._salas[1]['jogadores'] = ['Ana', 'Bob', 'Carlos', 'Dani']

    def test_suas_cartas_visíveis(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert len(estado['suas_cartas']) == 3
        assert all('????' not in c for c in estado['suas_cartas'])

    def test_outros_jogadores_presentes(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        nomes = [j['nome'] for j in estado['jogadores']]
        assert set(nomes) == {'Ana', 'Bob', 'Carlos', 'Dani'}

    def test_jogador_offline_marcado(self):
        online = {'Ana', 'Bob', 'Carlos'}  # Dani offline
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        dani = next(j for j in estado['jogadores'] if j['nome'] == 'Dani')
        assert dani['online'] is False

    def test_placar_presente(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert estado['placar'] == [0, 0]

    def test_vira_presente(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert estado['vira'] is not None

    def test_mao_de_ferro_esconde_cartas(self):
        self.jogo.placar = {0: 11, 1: 11}
        self.jogo.iniciar_mao()
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert all(c == '????' for c in estado['suas_cartas'])

    def test_mesa_vazia_no_inicio(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert estado['mesa'] == []

    def test_sala_e_tipo_corretos(self):
        online = {'Ana', 'Bob', 'Carlos', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Ana', 1, online)
        assert estado['sala'] == 1
        assert estado['tipo'] == 'normal'


# ------------------------------------------------------------------ #
#  enviar                                                             #
# ------------------------------------------------------------------ #

class TestEnviar:
    def test_envia_json_com_newline(self):
        conn = _mock_conn()
        srv.enviar(conn, {'tipo': 'ok'})
        conn.sendall.assert_called_once()
        data = conn.sendall.call_args[0][0].decode()
        assert data.endswith('\n')
        assert json.loads(data.strip()) == {'tipo': 'ok'}

    def test_nao_lanca_excecao_em_conexao_fechada(self):
        conn = _mock_conn()
        conn.sendall.side_effect = OSError()
        srv.enviar(conn, {'tipo': 'ok'})  # não deve lançar


# ------------------------------------------------------------------ #
#  entrar_sala                                                        #
# ------------------------------------------------------------------ #

class TestEntrarSala():
    def setup_method(self):
        srv._r = MagicMock()
        srv._r.sadd = MagicMock()
        srv._r.srem = MagicMock()
        srv._r.smembers = MagicMock(return_value=set())
        srv._r.exists = MagicMock(return_value=0)

    def test_sala_invalida(self):
        conn = _mock_conn()
        resultado = srv.entrar_sala('Ana', 99, conn)
        assert resultado is None

    def test_sala_cheia(self):
        srv._salas[1]['jogadores'] = ['A', 'B', 'C', 'D']
        conn = _mock_conn()
        resultado = srv.entrar_sala('Novo', 1, conn)
        assert resultado is None

    def test_partida_em_andamento(self):
        srv._salas[1]['status'] = 'jogando'
        srv._salas[1]['jogadores'] = ['A', 'B', 'C']
        conn = _mock_conn()
        resultado = srv.entrar_sala('Novo', 1, conn)
        assert resultado is None

    def test_entrada_bem_sucedida(self):
        conn = _mock_conn()
        with patch.object(srv, '_iniciar_jogo'):
            resultado = srv.entrar_sala('Ana', 1, conn)
        assert resultado == 1
        assert 'Ana' in srv._salas[1]['jogadores']
        assert srv._salas[1]['conexoes']['Ana'] == conn

    def test_jogador_ja_na_sala(self):
        srv._salas[1]['jogadores'] = ['Ana']
        srv._salas[1]['conexoes'] = {'Ana': _mock_conn()}
        conn = _mock_conn()
        resultado = srv.entrar_sala('Ana', 1, conn)
        assert resultado is None


# ------------------------------------------------------------------ #
#  processar_mensagem                                                 #
# ------------------------------------------------------------------ #

class TestProcessarMensagem:
    def setup_method(self):
        srv._r = MagicMock()
        srv._pg = MagicMock()
        srv._pg_lock = MagicMock()

    def test_listar_salas(self):
        conn = _mock_conn()
        srv.processar_mensagem({'tipo': 'listar_salas', 'usuario': 'Ana'}, 'Ana', None, conn)
        conn.sendall.assert_called_once()
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'salas'
        assert len(msg['lista']) == 16

    def test_tipo_desconhecido(self):
        conn = _mock_conn()
        srv.processar_mensagem({'tipo': 'invalido', 'usuario': 'Ana'}, 'Ana', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'erro'

    def test_meu_perfil(self):
        conn = _mock_conn()
        with patch('banco_postgres.obter_perfil', return_value={
            'nome': 'Ana', 'vitorias': 3, 'partidas': 5, 'derrotas': 2
        }):
            srv.processar_mensagem({'tipo': 'meu_perfil', 'usuario': 'Ana'}, 'Ana', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'perfil'
        assert msg['nome'] == 'Ana'

    def test_ranking(self):
        conn = _mock_conn()
        with patch('banco_postgres.obter_ranking', return_value=[
            {'nome': 'Ana', 'vitorias': 10}
        ]):
            srv.processar_mensagem({'tipo': 'ranking', 'usuario': 'Ana'}, 'Ana', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'ranking'

    def test_entrar_sala_sem_numero(self):
        conn = _mock_conn()
        srv.processar_mensagem({'tipo': 'entrar_sala', 'sala': 'abc', 'usuario': 'Ana'}, 'Ana', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'erro'
