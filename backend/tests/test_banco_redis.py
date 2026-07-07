import pytest
import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import fakeredis
import banco_redis as br


@pytest.fixture
def r():
    """Redis falso isolado por teste, com decode_responses=True."""
    return fakeredis.FakeRedis(decode_responses=True)


# ------------------------------------------------------------------ #
#  Sessões                                                            #
# ------------------------------------------------------------------ #

class TestSessoes:
    def test_salvar_e_obter_sessao(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        sessao = br.obter_sessao(r, 'tok1')
        assert sessao['nome'] == 'Almodenga'
        assert sessao['sala'] == ''

    def test_sessao_inexistente_retorna_none(self, r):
        assert br.obter_sessao(r, 'naoexiste') is None

    def test_sessao_existe(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        assert br.sessao_existe(r, 'tok1') is True
        assert br.sessao_existe(r, 'outro') is False

    def test_atualizar_sala(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        br.atualizar_sessao_sala(r, 'tok1', 3)
        sessao = br.obter_sessao(r, 'tok1')
        assert sessao['sala'] == '3'

    def test_atualizar_sala_para_lobby(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        br.atualizar_sessao_sala(r, 'tok1', 3)
        br.atualizar_sessao_sala(r, 'tok1', None)
        assert br.obter_sessao(r, 'tok1')['sala'] == ''

    def test_remover_sessao(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        br.remover_sessao(r, 'tok1', 'Almodenga')
        assert br.obter_sessao(r, 'tok1') is None

    def test_token_por_nome(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        assert br.token_por_nome(r, 'Almodenga') == 'tok1'

    def test_token_por_nome_inexistente(self, r):
        assert br.token_por_nome(r, 'Ninguem') is None

    def test_remover_sessao_limpa_indice_reverso(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        br.remover_sessao(r, 'tok1', 'Almodenga')
        assert br.token_por_nome(r, 'Almodenga') is None

    def test_sobrescrever_sessao(self, r):
        br.salvar_sessao(r, 'tok1', 'Almodenga')
        br.salvar_sessao(r, 'tok2', 'Almodenga')
        assert br.token_por_nome(r, 'Almodenga') == 'tok2'


# ------------------------------------------------------------------ #
#  Jogadores nas salas                                                #
# ------------------------------------------------------------------ #

class TestJogadoresSala:
    def test_entrar_e_listar(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 1, 'Baguga')
        jogadores = br.jogadores_na_sala(r, 1)
        assert set(jogadores) == {'Almodenga', 'Baguga'}

    def test_sala_vazia(self, r):
        assert br.jogadores_na_sala(r, 1) == []

    def test_num_jogadores(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 1, 'Baguga')
        assert br.num_jogadores_na_sala(r, 1) == 2

    def test_sair_da_sala(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 1, 'Baguga')
        br.sair_sala(r, 1, 'Almodenga')
        assert br.jogadores_na_sala(r, 1) == ['Baguga']

    def test_jogador_esta_na_sala(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        assert br.jogador_esta_na_sala(r, 1, 'Almodenga') is True
        assert br.jogador_esta_na_sala(r, 1, 'Baguga') is False

    def test_limpar_sala(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 1, 'Baguga')
        br.limpar_sala_jogadores(r, 1)
        assert br.jogadores_na_sala(r, 1) == []

    def test_salas_independentes(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 2, 'Baguga')
        assert br.jogadores_na_sala(r, 1) == ['Almodenga']
        assert br.jogadores_na_sala(r, 2) == ['Baguga']

    def test_mesmo_jogador_nao_duplica(self, r):
        br.entrar_sala(r, 1, 'Almodenga')
        br.entrar_sala(r, 1, 'Almodenga')
        assert br.num_jogadores_na_sala(r, 1) == 1


# ------------------------------------------------------------------ #
#  Estado do jogo                                                     #
# ------------------------------------------------------------------ #

class TestEstadoJogo:
    def _estado_exemplo(self):
        return {
            'sala_id': 3,
            'tipo': 'normal',
            'jogadores': ['Almodenga', 'Baguga', 'CharlesHenrique', 'Dante(banidodoceuedoinforno)'],
            'placar': {'0': 6, '1': 3},
            'status': 'jogando',
        }

    def test_salvar_e_obter(self, r):
        estado = self._estado_exemplo()
        br.salvar_estado_jogo(r, 3, estado)
        obtido = br.obter_estado_jogo(r, 3)
        assert obtido['sala_id'] == 3
        assert obtido['placar']['0'] == 6

    def test_estado_inexistente_retorna_none(self, r):
        assert br.obter_estado_jogo(r, 99) is None

    def test_estado_existe(self, r):
        br.salvar_estado_jogo(r, 3, self._estado_exemplo())
        assert br.estado_jogo_existe(r, 3) is True
        assert br.estado_jogo_existe(r, 99) is False

    def test_remover_estado(self, r):
        br.salvar_estado_jogo(r, 3, self._estado_exemplo())
        br.remover_estado_jogo(r, 3)
        assert br.obter_estado_jogo(r, 3) is None

    def test_sobrescrever_estado(self, r):
        br.salvar_estado_jogo(r, 3, self._estado_exemplo())
        novo = self._estado_exemplo()
        novo['placar'] = {'0': 9, '1': 6}
        br.salvar_estado_jogo(r, 3, novo)
        assert br.obter_estado_jogo(r, 3)['placar']['0'] == 9

    def test_definir_ttl(self, r):
        br.salvar_estado_jogo(r, 3, self._estado_exemplo())
        br.definir_ttl_estado(r, 3, 60)
        ttl = br.ttl_estado(r, 3)
        assert 0 < ttl <= 60

    def test_remover_ttl(self, r):
        br.salvar_estado_jogo(r, 3, self._estado_exemplo())
        br.definir_ttl_estado(r, 3, 60)
        br.remover_ttl_estado(r, 3)
        assert br.ttl_estado(r, 3) == -1  # sem TTL

    def test_estado_preserva_unicode(self, r):
        estado = self._estado_exemplo()
        estado['vira'] = '7♥'
        estado['manilhas'] = [['7', '♣'], ['7', '♥'], ['7', '♠'], ['7', '♦']]
        br.salvar_estado_jogo(r, 3, estado)
        obtido = br.obter_estado_jogo(r, 3)
        assert obtido['vira'] == '7♥'
        assert obtido['manilhas'][0] == ['7', '♣']

    def test_salas_independentes(self, r):
        e1 = self._estado_exemplo()
        e2 = self._estado_exemplo()
        e2['sala_id'] = 5
        br.salvar_estado_jogo(r, 3, e1)
        br.salvar_estado_jogo(r, 5, e2)
        assert br.obter_estado_jogo(r, 3)['sala_id'] == 3
        assert br.obter_estado_jogo(r, 5)['sala_id'] == 5


# ------------------------------------------------------------------ #
#  Desconexão                                                         #
# ------------------------------------------------------------------ #

class TestDesconexao:
    def test_registrar_desconexao(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        assert br.esta_desconectado(r, 'Almodenga') is True

    def test_nao_esta_desconectado(self, r):
        assert br.esta_desconectado(r, 'Almodenga') is False

    def test_obter_desconexao(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        info = br.obter_desconexao(r, 'Almodenga')
        assert info['sala'] == 3
        assert info['reconectou'] is False

    def test_obter_desconexao_inexistente(self, r):
        assert br.obter_desconexao(r, 'Almodenga') is None

    def test_marcar_reconectado(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        br.marcar_reconectado(r, 'Almodenga')
        info = br.obter_desconexao(r, 'Almodenga')
        assert info['reconectou'] is True

    def test_marcar_reconectado_sem_desconexao_nao_falha(self, r):
        br.marcar_reconectado(r, 'Ninguem')  # não deve lançar exceção

    def test_remover_desconexao(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        br.remover_desconexao(r, 'Almodenga')
        assert br.esta_desconectado(r, 'Almodenga') is False

    def test_tempo_restante(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        tempo = br.tempo_restante_desconexao(r, 'Almodenga')
        assert 0 < tempo <= br.DESCONEXAO_TTL

    def test_tempo_restante_inexistente(self, r):
        assert br.tempo_restante_desconexao(r, 'Almodenga') == -2

    def test_jogadores_diferentes_independentes(self, r):
        br.registrar_desconexao(r, 'Almodenga', 3)
        br.registrar_desconexao(r, 'Baguga', 5)
        assert br.obter_desconexao(r, 'Almodenga')['sala'] == 3
        assert br.obter_desconexao(r, 'Baguga')['sala'] == 5
