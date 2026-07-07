import pytest
import sys
import os
import json
import threading
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
    j = Jogo(sala_id=1, jogadores=['Almodenga', 'baguga', 'CharlesHenrique', 'Dani'], tipo='normal')
    j.iniciar_mao()
    return j


def _jogo_1v1():
    j = Jogo(sala_id=14, jogadores=['Almodenga', 'baguga'], tipo='1v1')
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
        srv._salas[1]['jogadores'] = ['Almodenga', 'baguga']
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
        srv._salas[1]['jogadores'] = ['Almodenga', 'baguga', 'CharlesHenrique', 'Dani']

    def test_suas_cartas_visíveis(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        assert len(estado['suas_cartas']) == 3
        assert all('????' not in c for c in estado['suas_cartas'])

    def test_outros_jogadores_presentes(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        nomes = [j['nome'] for j in estado['jogadores']]
        assert set(nomes) == {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}

    def test_jogador_offline_marcado(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique'}  # Dani offline
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        dani = next(j for j in estado['jogadores'] if j['nome'] == 'Dani')
        assert dani['online'] is False

    def test_placar_presente(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        assert estado['placar'] == [0, 0]

    def test_vira_presente(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        assert estado['vira'] is not None

    def test_mao_de_ferro_esconde_cartas(self):
        self.jogo.placar = {0: 11, 1: 11}
        self.jogo.iniciar_mao()
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        assert all(c == '????' for c in estado['suas_cartas'])

    def test_mesa_vazia_no_inicio(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
        assert estado['mesa'] == []

    def test_sala_e_tipo_corretos(self):
        online = {'Almodenga', 'baguga', 'CharlesHenrique', 'Dani'}
        estado = srv.montar_estado_para(self.jogo, 'Almodenga', 1, online)
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
        resultado = srv.entrar_sala('Almodenga', 99, conn)
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
            resultado = srv.entrar_sala('Almodenga', 1, conn)
        assert resultado == 1
        assert 'Almodenga' in srv._salas[1]['jogadores']
        assert srv._salas[1]['conexoes']['Almodenga'] == conn

    def test_jogador_ja_na_sala(self):
        srv._salas[1]['jogadores'] = ['Almodenga']
        srv._salas[1]['conexoes'] = {'Almodenga': _mock_conn()}
        conn = _mock_conn()
        resultado = srv.entrar_sala('Almodenga', 1, conn)
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
        srv.processar_mensagem({'tipo': 'listar_salas', 'usuario': 'Almodenga'}, 'Almodenga', None, conn)
        conn.sendall.assert_called_once()
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'salas'
        assert len(msg['lista']) == 16

    def test_tipo_desconhecido(self):
        conn = _mock_conn()
        srv.processar_mensagem({'tipo': 'invalido', 'usuario': 'Almodenga'}, 'Almodenga', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'erro'

    def test_meu_perfil(self):
        conn = _mock_conn()
        with patch('banco_postgres.obter_perfil', return_value={
            'nome': 'Almodenga', 'vitorias': 3, 'partidas': 5, 'derrotas': 2
        }):
            srv.processar_mensagem({'tipo': 'meu_perfil', 'usuario': 'Almodenga'}, 'Almodenga', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'perfil'
        assert msg['nome'] == 'Almodenga'

    def test_ranking(self):
        conn = _mock_conn()
        with patch('banco_postgres.obter_ranking', return_value=[
            {'nome': 'Almodenga', 'vitorias': 10}
        ]):
            srv.processar_mensagem({'tipo': 'ranking', 'usuario': 'Almodenga'}, 'Almodenga', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'ranking'

    def test_entrar_sala_sem_numero(self):
        conn = _mock_conn()
        srv.processar_mensagem({'tipo': 'entrar_sala', 'sala': 'abc', 'usuario': 'Almodenga'}, 'Almodenga', None, conn)
        msg = json.loads(conn.sendall.call_args[0][0].decode().strip())
        assert msg['tipo'] == 'erro'


# ------------------------------------------------------------------ #
#  Regressão: deadlock do _lock global em timeout/correr              #
# ------------------------------------------------------------------ #

def _run_com_timeout(func, args, limite=2):
    """Roda func em outra thread; falha o teste se ela travar (deadlock)."""
    import threading
    t = threading.Thread(target=func, args=args, daemon=True)
    t.start()
    t.join(limite)
    assert not t.is_alive(), 'deadlock: função não retornou a tempo'


class TestSemDeadlockNoLock:
    def setup_method(self):
        srv._r = MagicMock()
        srv._pg = MagicMock()

    def test_timeout_inatividade_na_propria_vez_nao_trava(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        vez = jogo.jogador_da_vez()

        _run_com_timeout(srv._timeout_inatividade, (1, vez))

        assert srv._lock.acquire(blocking=False)
        srv._lock.release()
        assert sala['status'] == 'pausada'

    def test_votar_correr_sala_normal_falta_parceiro_nao_trava(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        nome = jogo.jogadores[0]

        _run_com_timeout(srv._votar_correr, (nome, 1, True))

        assert srv._lock.acquire(blocking=False)
        srv._lock.release()
        assert sala['votos_correr'].get(nome) is True


# ------------------------------------------------------------------ #
#  W.O. por AFK após a única reconexão                                #
# ------------------------------------------------------------------ #

class TestAfkWo:
    def setup_method(self):
        srv._r = MagicMock()
        srv._pg = MagicMock()

    def test_timeout_apos_reconexao_nao_reabre_janela(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        vez = jogo.jogador_da_vez()
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        sala['ja_reconectou'] = {vez}

        with patch.object(srv, '_handle_desconexao') as mock_desconexao, \
             patch.object(srv, '_iniciar_timer_turno'):
            srv._timeout_inatividade(1, vez)

        mock_desconexao.assert_not_called()
        assert sala['afk_conta'].get(vez) == 1
        assert sala['status'] == 'jogando'

    def test_segundo_timeout_apos_reconexao_causa_wo(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        vez = jogo.jogador_da_vez()
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        sala['ja_reconectou'] = {vez}
        sala['afk_conta'] = {vez: 1}

        with patch.object(srv, '_encerrar_jogo') as mock_encerrar:
            srv._timeout_inatividade(1, vez)

        mock_encerrar.assert_called_once()
        sala_id, dupla_vencedora, motivo = mock_encerrar.call_args[0]
        assert sala_id == 1
        assert motivo == 'wo'
        assert dupla_vencedora != jogo.duplas[vez]

    def test_jogar_carta_reseta_contagem_afk(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        vez = jogo.jogador_da_vez()
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        sala['afk_conta'] = {vez: 1}

        with patch.object(srv, '_processar_resultado_acao'):
            srv._jogar_carta(vez, 1, 0, coberta=False)

        assert vez not in sala['afk_conta']


# ------------------------------------------------------------------ #
#  Regressão: desconexão dupla e timers de reconexão                  #
# ------------------------------------------------------------------ #

class TestDesconexaoDupla:
    def setup_method(self):
        srv._r = MagicMock()
        srv._pg = MagicMock()

    def teardown_method(self):
        # Cancela timers reais criados pelos testes
        for t in list(srv._timers_desconexao.values()):
            t.cancel()
        srv._timers_desconexao.clear()

    def _sala_em_jogo(self):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        sala['conexoes'] = {n: _mock_conn() for n in jogo.jogadores}
        return jogo, sala

    def test_segunda_chamada_nao_cria_segundo_timer(self):
        # Kick por inatividade fecha o socket, o que faz o handler da
        # conexão chamar _handle_desconexao de novo. O segundo timer
        # sobrescrevia o primeiro no dict, deixando um timer órfão que
        # causava W.O. aos 60s mesmo após reconexão bem-sucedida.
        jogo, sala = self._sala_em_jogo()
        nome = jogo.jogadores[0]

        srv._handle_desconexao(nome, 1)
        timer1 = srv._timers_desconexao.get(nome)
        assert timer1 is not None

        srv._handle_desconexao(nome, 1)
        assert srv._timers_desconexao.get(nome) is timer1

    def test_timeout_sem_reconexao_remove_timer_do_dict(self):
        jogo, sala = self._sala_em_jogo()
        nome = jogo.jogadores[0]

        srv._handle_desconexao(nome, 1)
        assert nome in srv._timers_desconexao

        with patch.object(srv, '_encerrar_jogo'):
            srv._timeout_sem_reconexao(nome, 1)

        assert nome not in srv._timers_desconexao

    def test_encerrar_jogo_cancela_timers_de_desconexao(self):
        jogo, sala = self._sala_em_jogo()
        nome = jogo.jogadores[0]

        srv._handle_desconexao(nome, 1)
        assert nome in srv._timers_desconexao

        srv._pg_lock = threading.Lock()
        with patch.object(srv.bp, 'encerrar_partida'), \
             patch.object(srv.bp, 'registrar_vitoria'), \
             patch.object(srv.bp, 'registrar_derrota'):
            srv._encerrar_jogo(1, 0, 'completa')

        assert nome not in srv._timers_desconexao


class TestReconexaoTimerTurno:
    def setup_method(self):
        srv._r = MagicMock()
        srv._pg = MagicMock()

    def _sala_com_desconectado(self, nome_off):
        jogo = _jogo_normal()
        sala = srv._salas[1]
        sala['jogadores'] = list(jogo.jogadores)
        sala['jogo'] = jogo
        sala['status'] = 'jogando'
        sala['conexoes'] = {
            n: _mock_conn() for n in jogo.jogadores if n != nome_off
        }
        return jogo, sala

    def test_reconexao_fora_da_vez_nao_reinicia_timer_turno(self):
        # O timer de quem está na vez continua valendo; reiniciá-lo para
        # o reconectado cancelava o timer certo e expulsava o reconectado
        # 30s depois mesmo sem ser a vez dele.
        jogo, sala = self._sala_com_desconectado(None)
        vez = jogo.jogador_da_vez()
        outro = next(n for n in jogo.jogadores if n != vez)
        del sala['conexoes'][outro]

        with patch.object(srv, '_iniciar_timer_turno') as mock_timer, \
             patch.object(srv, '_cancelar_timer_desconexao'), \
             patch.object(srv.br, 'esta_desconectado', return_value=True), \
             patch.object(srv.br, 'marcar_reconectado'), \
             patch.object(srv.br, 'remover_ttl_estado'):
            resultado = srv.entrar_sala(outro, 1, _mock_conn())

        assert resultado == 1
        assert outro in sala['conexoes']
        mock_timer.assert_not_called()
        assert sala['status'] == 'jogando'

    def test_reconexao_na_vez_retoma_jogo_pausado(self):
        jogo, sala = self._sala_com_desconectado(None)
        vez = jogo.jogador_da_vez()
        del sala['conexoes'][vez]
        sala['status'] = 'pausada'
        jogo.status = 'pausada'

        with patch.object(srv, '_iniciar_timer_turno') as mock_timer, \
             patch.object(srv, '_cancelar_timer_desconexao'), \
             patch.object(srv.br, 'esta_desconectado', return_value=True), \
             patch.object(srv.br, 'marcar_reconectado'), \
             patch.object(srv.br, 'remover_ttl_estado'):
            resultado = srv.entrar_sala(vez, 1, _mock_conn())

        assert resultado == 1
        assert sala['status'] == 'jogando'
        assert jogo.status == 'jogando'
        mock_timer.assert_called_once_with(1, vez, srv.TIMER_DECISAO)
