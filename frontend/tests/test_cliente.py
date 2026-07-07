import pytest
import sys
import os
import json
import time
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cliente import Cliente, MAX_CHAT


# ------------------------------------------------------------------ #
#  Fixture                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def c():
    """Cliente sem conexão real para testes unitários."""
    cliente = Cliente()
    return cliente


def _processar(c, msg):
    """Coloca mensagem na fila e processa."""
    c._fila.put(msg)
    c.processar_fila()


# ------------------------------------------------------------------ #
#  Estado inicial                                                     #
# ------------------------------------------------------------------ #

class TestEstadoInicial:
    def test_tela_inicial_e_inicio(self, c):
        assert c.tela == 'inicio'

    def test_sem_nome_inicial(self, c):
        assert c.nome is None

    def test_sem_sala_inicial(self, c):
        assert c.sala_id is None

    def test_chat_vazio(self, c):
        assert c.chat_msgs == []

    def test_status_vazio(self, c):
        assert c.status_msg == ''

    def test_timer_zerado(self, c):
        assert c.timer_restante() == 0


# ------------------------------------------------------------------ #
#  Mensagens tipo 'ok'                                                #
# ------------------------------------------------------------------ #

class TestMsgOk:
    def test_ok_sem_token_atualiza_status(self, c):
        _processar(c, {'tipo': 'ok', 'mensagem': 'Cadastro realizado!'})
        assert c.status_msg == 'Cadastro realizado!'
        assert c.tela == 'inicio'

    def test_ok_com_token_vai_para_lobby(self, c):
        _processar(c, {'tipo': 'ok', 'mensagem': 'Bem-vindo!', 'token': 'abc123'})
        assert c.tela == 'lobby'

    def test_ok_com_token_atualiza_status(self, c):
        _processar(c, {'tipo': 'ok', 'mensagem': 'Bem-vindo!', 'token': 'abc123'})
        assert c.status_msg == 'Bem-vindo!'


# ------------------------------------------------------------------ #
#  Mensagens tipo 'erro'                                              #
# ------------------------------------------------------------------ #

class TestMsgErro:
    def test_erro_atualiza_status(self, c):
        _processar(c, {'tipo': 'erro', 'mensagem': 'Usuário não encontrado'})
        assert '[ERRO]' in c.status_msg
        assert 'Usuário não encontrado' in c.status_msg

    def test_erro_nao_muda_tela(self, c):
        c.tela = 'login'
        _processar(c, {'tipo': 'erro', 'mensagem': 'Senha incorreta'})
        assert c.tela == 'login'


# ------------------------------------------------------------------ #
#  Mensagens tipo 'salas'                                             #
# ------------------------------------------------------------------ #

class TestMsgSalas:
    def test_lista_de_salas_salva(self, c):
        lista = [{'id': 1, 'tipo': 'normal', 'jogadores': 2, 'max': 4, 'status': 'aguardando'}]
        _processar(c, {'tipo': 'salas', 'lista': lista})
        assert c.lista_salas == lista

    def test_muda_tela_para_salas(self, c):
        _processar(c, {'tipo': 'salas', 'lista': []})
        assert c.tela == 'salas'

    def test_lista_vazia(self, c):
        _processar(c, {'tipo': 'salas', 'lista': []})
        assert c.lista_salas == []


# ------------------------------------------------------------------ #
#  Mensagens tipo 'perfil'                                            #
# ------------------------------------------------------------------ #

class TestMsgPerfil:
    def test_perfil_salvo(self, c):
        _processar(c, {'tipo': 'perfil', 'nome': 'Ana', 'partidas': 10, 'vitorias': 6, 'derrotas': 4})
        assert c.perfil is not None
        assert c.perfil['nome'] == 'Ana'
        assert c.perfil['vitorias'] == 6

    def test_muda_tela_para_perfil(self, c):
        _processar(c, {'tipo': 'perfil', 'nome': 'Ana', 'partidas': 0, 'vitorias': 0, 'derrotas': 0})
        assert c.tela == 'perfil'


# ------------------------------------------------------------------ #
#  Mensagens tipo 'ranking'                                           #
# ------------------------------------------------------------------ #

class TestMsgRanking:
    def test_ranking_salvo(self, c):
        lista = [{'nome': 'Bob', 'vitorias': 20}, {'nome': 'Ana', 'vitorias': 15}]
        _processar(c, {'tipo': 'ranking', 'lista': lista})
        assert c.ranking_lista[0]['nome'] == 'Bob'

    def test_muda_tela_para_ranking(self, c):
        _processar(c, {'tipo': 'ranking', 'lista': []})
        assert c.tela == 'ranking'


# ------------------------------------------------------------------ #
#  Mensagens tipo 'estado_jogo'                                       #
# ------------------------------------------------------------------ #

class TestMsgEstadoJogo:
    def test_estado_salvo(self, c):
        dados = {'sala': 3, 'rodada_atual': 1, 'mao_valor': 3}
        _processar(c, {'tipo': 'estado_jogo', 'dados': dados})
        assert c.estado_jogo == dados

    def test_muda_tela_para_jogo(self, c):
        _processar(c, {'tipo': 'estado_jogo', 'dados': {}})
        assert c.tela == 'jogo'

    def test_estado_anterior_substituido(self, c):
        _processar(c, {'tipo': 'estado_jogo', 'dados': {'sala': 1}})
        _processar(c, {'tipo': 'estado_jogo', 'dados': {'sala': 2}})
        assert c.estado_jogo['sala'] == 2


# ------------------------------------------------------------------ #
#  Mensagens tipo 'chat'                                              #
# ------------------------------------------------------------------ #

class TestMsgChat:
    def test_mensagem_adicionada(self, c):
        _processar(c, {'tipo': 'chat', 'de': 'Ana', 'mensagem': 'oi!'})
        assert any('Ana' in m and 'oi!' in m for m in c.chat_msgs)

    def test_multiplas_mensagens(self, c):
        _processar(c, {'tipo': 'chat', 'de': 'Ana', 'mensagem': 'oi'})
        _processar(c, {'tipo': 'chat', 'de': 'Bob', 'mensagem': 'tudo bem'})
        assert len(c.chat_msgs) == 2

    def test_limite_maximo_chat(self, c):
        for i in range(MAX_CHAT + 5):
            _processar(c, {'tipo': 'chat', 'de': 'X', 'mensagem': str(i)})
        assert len(c.chat_msgs) == MAX_CHAT

    def test_mensagem_mais_antiga_removida_quando_cheio(self, c):
        for i in range(MAX_CHAT):
            _processar(c, {'tipo': 'chat', 'de': 'X', 'mensagem': str(i)})
        _processar(c, {'tipo': 'chat', 'de': 'X', 'mensagem': 'nova'})
        assert not any('X: 0' in m for m in c.chat_msgs)


# ------------------------------------------------------------------ #
#  Mensagens tipo 'aviso'                                             #
# ------------------------------------------------------------------ #

class TestMsgAviso:
    def test_aviso_adicionado_ao_chat(self, c):
        _processar(c, {'tipo': 'aviso', 'mensagem': 'Truco pedido!'})
        assert any('Truco pedido!' in m for m in c.chat_msgs)

    def test_aviso_tem_prefixo(self, c):
        _processar(c, {'tipo': 'aviso', 'mensagem': 'Teste'})
        assert any(m.startswith('>>>') for m in c.chat_msgs)


# ------------------------------------------------------------------ #
#  Mensagens tipo 'desconexao'                                        #
# ------------------------------------------------------------------ #

class TestMsgDesconexao:
    def test_desconexao_adicionada_ao_chat(self, c):
        _processar(c, {'tipo': 'desconexao', 'jogador': 'Bob', 'tempo_restante': 60})
        assert any('Bob' in m and 'desconectou' in m for m in c.chat_msgs)

    def test_desconexao_sem_tempo_usa_default(self, c):
        _processar(c, {'tipo': 'desconexao', 'jogador': 'Bob'})
        assert any('60s' in m for m in c.chat_msgs)


# ------------------------------------------------------------------ #
#  Mensagens tipo 'timer_turno'                                       #
# ------------------------------------------------------------------ #

class TestMsgTimerTurno:
    def test_timer_salvo(self, c):
        _processar(c, {'tipo': 'timer_turno', 'segundos': 45, 'jogador': 'Ana'})
        assert c.timer_total == 45
        assert c.timer_jogador == 'Ana'

    def test_timer_restante_logo_apos_receber(self, c):
        _processar(c, {'tipo': 'timer_turno', 'segundos': 45, 'jogador': 'Ana'})
        restante = c.timer_restante()
        assert 43 <= restante <= 45

    def test_timer_zero_quando_nao_iniciado(self, c):
        assert c.timer_restante() == 0

    def test_timer_nao_negativo(self, c):
        # Simula timer que já expirou
        c.timer_total  = 10
        c.timer_inicio = time.time() - 20
        assert c.timer_restante() == 0


# ------------------------------------------------------------------ #
#  Mensagens tipo 'decisao_pendente'                                  #
# ------------------------------------------------------------------ #

class TestMsgDecisaoPendente:
    def test_decisao_adicionada_ao_chat(self, c):
        _processar(c, {'tipo': 'decisao_pendente', 'acao': 'truco', 'timer': 30})
        assert any('truco' in m.lower() for m in c.chat_msgs)

    def test_timer_na_mensagem(self, c):
        _processar(c, {'tipo': 'decisao_pendente', 'acao': 'correr', 'timer': 30})
        assert any('30s' in m for m in c.chat_msgs)


# ------------------------------------------------------------------ #
#  Mensagens tipo 'fim_partida'                                       #
# ------------------------------------------------------------------ #

class TestMsgFimPartida:
    def test_volta_para_lobby(self, c):
        c.tela = 'jogo'
        _processar(c, {'tipo': 'fim_partida', 'resultado': 'vitoria', 'motivo': 'pontos'})
        assert c.tela == 'lobby'

    def test_estado_jogo_limpo(self, c):
        c.estado_jogo = {'sala': 1}
        _processar(c, {'tipo': 'fim_partida', 'resultado': 'derrota', 'motivo': 'wo'})
        assert c.estado_jogo is None

    def test_sala_limpa(self, c):
        c.sala_id = 5
        _processar(c, {'tipo': 'fim_partida', 'resultado': 'vitoria', 'motivo': 'pontos'})
        assert c.sala_id is None

    def test_resultado_maiusculo_no_status(self, c):
        _processar(c, {'tipo': 'fim_partida', 'resultado': 'vitoria', 'motivo': 'pontos'})
        assert 'VITORIA' in c.status_msg

    def test_motivo_no_status(self, c):
        _processar(c, {'tipo': 'fim_partida', 'resultado': 'derrota', 'motivo': 'wo'})
        assert 'wo' in c.status_msg

    def test_chat_limpo_ao_fim_da_partida(self, c):
        # Chat é por partida: mensagens não sobrevivem para a próxima
        _processar(c, {'tipo': 'chat', 'de': 'Ana', 'mensagem': 'boa sorte!'})
        _processar(c, {'tipo': 'aviso', 'mensagem': 'Truco pedido!'})
        assert len(c.chat_msgs) == 2

        _processar(c, {'tipo': 'fim_partida', 'resultado': 'vitoria', 'motivo': 'pontos'})

        assert c.chat_msgs == []


# ------------------------------------------------------------------ #
#  processar_fila                                                     #
# ------------------------------------------------------------------ #

class TestProcessarFila:
    def test_retorna_true_quando_ha_mensagens(self, c):
        c._fila.put({'tipo': 'ok', 'mensagem': 'teste'})
        assert c.processar_fila() is True

    def test_retorna_false_quando_fila_vazia(self, c):
        assert c.processar_fila() is False

    def test_processa_multiplas_mensagens(self, c):
        c._fila.put({'tipo': 'chat', 'de': 'A', 'mensagem': '1'})
        c._fila.put({'tipo': 'chat', 'de': 'B', 'mensagem': '2'})
        c.processar_fila()
        assert len(c.chat_msgs) == 2

    def test_msg_tipo_desconhecido_ignorada(self, c):
        c._fila.put({'tipo': 'tipo_que_nao_existe', 'dados': 'x'})
        c.processar_fila()  # não deve lançar exceção
        assert c.status_msg == ''


# ------------------------------------------------------------------ #
#  Regressão: detecção de conexão perdida e reconexão                 #
# ------------------------------------------------------------------ #

class TestDeteccaoDesconexao:
    def test_receber_marca_desconectado_quando_socket_cai(self, c):
        local, remoto = socket.socketpair()
        c.conn = local
        c.tela = 'jogo'
        remoto.close()  # simula o broker fechando a conexão

        c._receber()  # recv retorna EOF imediatamente, thread encerra sozinha

        assert c.conectado is False
        assert c.tela == 'desconectado'
        local.close()

    def test_receber_nao_muda_tela_durante_login(self, c):
        local, remoto = socket.socketpair()
        c.conn = local
        c.tela = 'login'
        remoto.close()

        c._receber()

        assert c.conectado is False
        assert c.tela == 'login'
        local.close()

    def test_receber_no_lobby_tambem_vai_para_desconectado(self, c):
        local, remoto = socket.socketpair()
        c.conn = local
        c.tela = 'lobby'
        remoto.close()

        c._receber()

        assert c.conectado is False
        assert c.tela == 'desconectado'
        local.close()


class TestReconectar:
    def test_reconectar_fecha_conexao_antiga_e_reseta_estado(self, c, monkeypatch):
        local, remoto = socket.socketpair()
        c.conn = local
        c.estado_jogo = {'foo': 'bar'}
        c.status_msg = '[ERRO] antigo'

        chamado = {}
        def fake_conectar():
            chamado['ok'] = True
            c.conectado = True
        monkeypatch.setattr(c, 'conectar', fake_conectar)

        c.reconectar()

        assert chamado.get('ok') is True
        assert c.estado_jogo is None
        assert c.status_msg == ''
        # Sem credenciais salvas: volta para o início
        assert c.tela == 'inicio'
        with pytest.raises(OSError):
            local.send(b'x')  # conexão antiga deve ter sido fechada
        remoto.close()

    def test_reconectar_trata_falha_de_conexao(self, c, monkeypatch):
        def fake_conectar():
            raise OSError('recusado')
        monkeypatch.setattr(c, 'conectar', fake_conectar)

        c.reconectar()

        assert c.conectado is False
        assert '[ERRO]' in c.status_msg
        assert c.tela == 'desconectado'

    def test_reabrir_conexao_nao_mexe_na_tela(self, c, monkeypatch):
        c.tela = 'jogo'
        monkeypatch.setattr(c, 'conectar', lambda: None)

        c._reabrir_conexao()

        # _reabrir_conexao() não decide tela; quem decide é reconectar()
        assert c.tela == 'jogo'

    def test_reconectar_reloga_e_volta_para_partida(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', '123', 3
        c.tela = 'desconectado'

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Bem-vindo, Ana!', 'token': 'abc'})
            elif msg['tipo'] == 'entrar_sala':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Reconectado!'})
                c._fila.put({'tipo': 'estado_jogo', 'dados': {'sala': 3}})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'jogo'
        assert c.sala_id == 3

    def test_reconectar_sem_sala_fica_no_lobby(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', '123', None
        c.tela = 'desconectado'

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Bem-vindo, Ana!', 'token': 'abc'})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'lobby'

    def test_reconectar_com_reconexao_ja_usada_cai_no_lobby(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', '123', 3
        c.tela = 'desconectado'

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Bem-vindo, Ana!', 'token': 'abc'})
            elif msg['tipo'] == 'entrar_sala':
                c._fila.put({'tipo': 'erro', 'mensagem': 'Reconexão já utilizada nesta partida'})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'lobby'
        assert c.sala_id is None
        assert '[ERRO]' in c.status_msg

    def test_reconectar_com_sala_reiniciada_vai_para_espera(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', '123', 3
        c.tela = 'desconectado'
        c.chat_msgs = ['Ana: mensagem da partida anterior']

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Bem-vindo, Ana!', 'token': 'abc'})
            elif msg['tipo'] == 'entrar_sala':
                # Partida acabou enquanto desconectado: entrou como novo
                c._fila.put({'tipo': 'ok', 'mensagem': 'Entrou na Sala 3'})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'espera_sala'
        assert c.sala_id == 3
        assert c.chat_msgs == []  # partida nova: chat limpo

    def test_reconectar_na_mesma_partida_mantem_chat(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', '123', 3
        c.tela = 'desconectado'
        c.chat_msgs = ['Bob: boa sorte!']

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Bem-vindo, Ana!', 'token': 'abc'})
            elif msg['tipo'] == 'entrar_sala':
                c._fila.put({'tipo': 'ok', 'mensagem': 'Reconectado!'})
                c._fila.put({'tipo': 'estado_jogo', 'dados': {'sala': 3}})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'jogo'
        assert 'Bob: boa sorte!' in c.chat_msgs  # mesma partida: chat preservado

    def test_reconectar_com_login_invalido_volta_para_desconectado(self, c, monkeypatch):
        monkeypatch.setattr(c, 'conectar', lambda: None)
        c.nome, c.senha, c.sala_id = 'Ana', 'senha_trocada', 3
        c.tela = 'desconectado'

        def fake_enviar(msg):
            if msg['tipo'] == 'login':
                c._fila.put({'tipo': 'erro', 'mensagem': 'Usuário ou senha inválidos'})
        monkeypatch.setattr(c, 'enviar', fake_enviar)

        c.reconectar()

        assert c.tela == 'desconectado'
        assert '[ERRO]' in c.status_msg
