import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from jogo import (
    criar_baralho, carta_str, determinar_manilhas, forca_carta,
    vencedor_rodada, vencedor_mao, proximo_valor_truco, Jogo,
    ORDEM_CARTAS, NAIPES, PONTOS_MAXIMOS
)


# ------------------------------------------------------------------ #
#  Baralho                                                            #
# ------------------------------------------------------------------ #

class TestBaralho:
    def test_tamanho_baralho(self):
        b = criar_baralho()
        assert len(b) == 40

    def test_sem_repeticoes(self):
        b = criar_baralho()
        assert len(set(b)) == 40

    def test_cartas_validas(self):
        b = criar_baralho()
        for valor, naipe in b:
            assert valor in ORDEM_CARTAS
            assert naipe in NAIPES

    def test_carta_str(self):
        assert carta_str(('3', '♣')) == '3♣'
        assert carta_str(('Q', '♥')) == 'Q♥'


# ------------------------------------------------------------------ #
#  Manilhas                                                           #
# ------------------------------------------------------------------ #

class TestManilhas:
    def test_manilha_do_6(self):
        vira = ('6', '♣')
        manilhas = determinar_manilhas(vira)
        assert all(m[0] == '7' for m in manilhas)

    def test_manilha_do_3(self):
        # Após o 3 vem o 4
        vira = ('3', '♦')
        manilhas = determinar_manilhas(vira)
        assert all(m[0] == '4' for m in manilhas)

    def test_manilha_do_7(self):
        vira = ('7', '♠')
        manilhas = determinar_manilhas(vira)
        assert all(m[0] == 'Q' for m in manilhas)

    def test_quatro_manilhas(self):
        vira = ('1', '♣')
        manilhas = determinar_manilhas(vira)
        assert len(manilhas) == 4
        naipes = [m[1] for m in manilhas]
        assert set(naipes) == set(NAIPES)


# ------------------------------------------------------------------ #
#  Força das cartas                                                   #
# ------------------------------------------------------------------ #

class TestForcaCarta:
    def setup_method(self):
        self.vira = ('6', '♣')
        self.manilhas = determinar_manilhas(self.vira)  # manilhas são os 7s

    def test_manilha_maior_que_carta_normal(self):
        manilha = ('7', '♣')
        normal = ('3', '♠')
        assert forca_carta(manilha, self.manilhas) > forca_carta(normal, self.manilhas)

    def test_ordem_naipes_manilha(self):
        zap = ('7', '♣')
        copas = ('7', '♥')
        espadas = ('7', '♠')
        ouros = ('7', '♦')
        assert (forca_carta(zap, self.manilhas) >
                forca_carta(copas, self.manilhas) >
                forca_carta(espadas, self.manilhas) >
                forca_carta(ouros, self.manilhas))

    def test_ordem_cartas_normais(self):
        manilhas = []
        tres = forca_carta(('3', '♣'), manilhas)
        dois = forca_carta(('2', '♣'), manilhas)
        asso = forca_carta(('1', '♣'), manilhas)
        quatro = forca_carta(('4', '♣'), manilhas)
        assert tres > dois > asso > quatro


# ------------------------------------------------------------------ #
#  Vencedor de rodada                                                 #
# ------------------------------------------------------------------ #

class TestVencedorRodada:
    def setup_method(self):
        self.vira = ('6', '♣')
        self.manilhas = determinar_manilhas(self.vira)

    def test_carta_mais_alta_vence(self):
        jogadas = [('Ana', ('3', '♣')), ('Bob', ('2', '♣'))]
        assert vencedor_rodada(jogadas, self.manilhas) == 'Ana'

    def test_manilha_vence_carta_normal(self):
        jogadas = [('Ana', ('3', '♣')), ('Bob', ('7', '♠'))]
        assert vencedor_rodada(jogadas, self.manilhas) == 'Bob'

    def test_empate_retorna_none(self):
        jogadas = [('Ana', ('3', '♣')), ('Bob', ('3', '♥'))]
        assert vencedor_rodada(jogadas, self.manilhas) is None

    def test_carta_coberta_perde(self):
        jogadas = [('Ana', None), ('Bob', ('4', '♣'))]
        assert vencedor_rodada(jogadas, self.manilhas) == 'Bob'

    def test_quatro_jogadores(self):
        jogadas = [
            ('A', ('4', '♣')),
            ('B', ('5', '♣')),
            ('C', ('3', '♣')),
            ('D', ('2', '♣')),
        ]
        assert vencedor_rodada(jogadas, self.manilhas) == 'C'

    def test_zap_vence_tudo(self):
        jogadas = [('A', ('3', '♣')), ('B', ('7', '♣'))]  # 7♣ é o zap
        assert vencedor_rodada(jogadas, self.manilhas) == 'B'


# ------------------------------------------------------------------ #
#  Vencedor de mão                                                    #
# ------------------------------------------------------------------ #

class TestVencedorMao:
    def setup_method(self):
        # dupla 0: Ana, Carlos | dupla 1: Bob, Dani
        self.duplas = {'Ana': 0, 'Bob': 1, 'Carlos': 0, 'Dani': 1}

    def test_vence_duas_rodadas(self):
        resultados = ['Ana', 'Carlos']
        assert vencedor_mao(resultados, self.duplas) == 0

    def test_adversario_vence_duas(self):
        resultados = ['Bob', 'Dani']
        assert vencedor_mao(resultados, self.duplas) == 1

    def test_empate_na_primeira_quem_vence_a_segunda_leva(self):
        resultados = [None, 'Bob']
        assert vencedor_mao(resultados, self.duplas) == 1

    def test_empate_na_segunda_quem_venceu_a_primeira_leva(self):
        resultados = ['Ana', None]
        assert vencedor_mao(resultados, self.duplas) == 0

    def test_empate_na_terceira_quem_venceu_a_primeira_leva(self):
        resultados = ['Ana', 'Bob', None]
        assert vencedor_mao(resultados, self.duplas) == 0

    def test_todas_empatam_ninguem_ganha(self):
        resultados = [None, None, None]
        assert vencedor_mao(resultados, self.duplas) is None

    def test_mao_nao_encerrada(self):
        resultados = ['Ana']
        assert vencedor_mao(resultados, self.duplas) is None


# ------------------------------------------------------------------ #
#  Truco — valores                                                    #
# ------------------------------------------------------------------ #

class TestProximoValorTruco:
    def test_sequencia_completa(self):
        assert proximo_valor_truco(1) == 3
        assert proximo_valor_truco(3) == 6
        assert proximo_valor_truco(6) == 9
        assert proximo_valor_truco(9) == 12
        assert proximo_valor_truco(12) is None


# ------------------------------------------------------------------ #
#  Classe Jogo — fluxo básico                                         #
# ------------------------------------------------------------------ #

def _criar_jogo_normal():
    return Jogo(sala_id=1, jogadores=['Ana', 'Bob', 'Carlos', 'Dani'], tipo='normal')

def _criar_jogo_1v1():
    return Jogo(sala_id=14, jogadores=['Ana', 'Bob'], tipo='1v1')


class TestJogoInicializacao:
    def test_duplas_normais(self):
        j = _criar_jogo_normal()
        assert j.duplas['Ana'] == 0
        assert j.duplas['Bob'] == 1
        assert j.duplas['Carlos'] == 0
        assert j.duplas['Dani'] == 1

    def test_duplas_1v1(self):
        j = _criar_jogo_1v1()
        assert j.duplas['Ana'] == 0
        assert j.duplas['Bob'] == 1

    def test_placar_inicial(self):
        j = _criar_jogo_normal()
        assert j.placar == {0: 0, 1: 0}

    def test_status_inicial(self):
        j = _criar_jogo_normal()
        assert j.status == 'aguardando'


class TestJogoIniciarMao:
    def test_cartas_distribuidas(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        for nome in j.jogadores:
            assert len(j.maos[nome]) == 3

    def test_vira_definida(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        assert j.vira is not None
        assert j.vira[0] in ORDEM_CARTAS

    def test_manilhas_definidas(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        assert len(j.manilhas) == 4

    def test_valor_mao_inicial(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        assert j.valor_mao == 1

    def test_status_jogando(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        assert j.status == 'jogando'

    def test_mao_de_11_valor_3(self):
        j = _criar_jogo_normal()
        j.placar[0] = 11
        j.iniciar_mao()
        assert j.valor_mao == 3

    def test_mao_de_ferro_valor_3(self):
        j = _criar_jogo_normal()
        j.placar[0] = 11
        j.placar[1] = 11
        j.iniciar_mao()
        assert j.valor_mao == 3


class TestJogoJogarCarta:
    def setup_method(self):
        self.j = _criar_jogo_normal()
        self.j.iniciar_mao()

    def test_nao_e_sua_vez(self):
        res = self.j.jogar_carta('Bob', 0)
        assert res['ok'] is False

    def test_jogar_carta_valida(self):
        primeiro = self.j.jogador_da_vez()
        res = self.j.jogar_carta(primeiro, 0)
        assert res['ok'] is True
        assert len(self.j.maos[primeiro]) == 2

    def test_indice_invalido(self):
        primeiro = self.j.jogador_da_vez()
        res = self.j.jogar_carta(primeiro, 10)
        assert res['ok'] is False

    def test_jogar_coberta(self):
        primeiro = self.j.jogador_da_vez()
        res = self.j.jogar_carta(primeiro, 0, coberta=True)
        assert res['ok'] is True
        assert res['coberta'] is True

    def test_rodada_encerra_com_todos(self):
        j = self.j
        for nome in j.jogadores:
            # força a vez (hack de teste)
            j.vez = j.jogadores.index(nome)
            res = j.jogar_carta(nome, 0)
        assert 'rodada_encerrada' in res
        assert res['rodada_encerrada'] is True


class TestJogoTruco:
    def setup_method(self):
        self.j = _criar_jogo_normal()
        self.j.iniciar_mao()

    def test_pedir_truco(self):
        res = self.j.pedir_truco('Ana')
        assert res['ok'] is True
        assert res['valor_proposto'] == 3
        assert self.j.status == 'truco_pendente'

    def test_mesma_dupla_nao_pode_pedir_novamente(self):
        self.j.pedir_truco('Ana')
        res = self.j.pedir_truco('Carlos')
        assert res['ok'] is False

    def test_aceitar_truco(self):
        self.j.pedir_truco('Ana')
        res = self.j.responder_truco('Bob', 'aceitar')
        assert res['ok'] is True
        assert self.j.valor_mao == 3
        assert self.j.status == 'jogando'

    def test_correr_do_truco(self):
        self.j.pedir_truco('Ana')
        res = self.j.responder_truco('Bob', 'correr')
        assert res['ok'] is True
        assert res['pontos'] == 1  # valor atual antes do truco
        assert self.j.placar[0] == 1  # dupla 0 (Ana) ganhou

    def test_aumentar_truco(self):
        self.j.pedir_truco('Ana')
        res = self.j.responder_truco('Bob', 'aumentar')
        assert res['ok'] is True
        assert self.j.valor_mao == 3   # aceita o truco
        assert self.j.valor_proposto == 6
        assert self.j.dupla_pediu_truco == 1  # dupla 1 (Bob) agora pediu

    def test_sequencia_completa_truco(self):
        j = self.j
        j.pedir_truco('Ana')        # propõe 3
        j.responder_truco('Bob', 'aumentar')   # aceita 3, propõe 6
        j.responder_truco('Ana', 'aumentar')   # aceita 6, propõe 9
        j.responder_truco('Bob', 'aumentar')   # aceita 9, propõe 12
        assert j.valor_mao == 9
        assert j.valor_proposto == 12
        res = j.responder_truco('Ana', 'aceitar')
        assert j.valor_mao == 12

    def test_nao_pode_aumentar_alem_de_12(self):
        j = self.j
        j.pedir_truco('Ana')
        j.responder_truco('Bob', 'aumentar')
        j.responder_truco('Ana', 'aumentar')
        j.responder_truco('Bob', 'aumentar')
        j.responder_truco('Ana', 'aceitar')  # aceita 12
        # não há mais truco para pedir
        res = j.pedir_truco('Bob')
        assert res['ok'] is False

    def test_mao_de_11_truco_perde_jogo(self):
        j = self.j
        j.placar[0] = 11
        j.iniciar_mao()
        res = j.pedir_truco('Ana')  # dupla 0 tem 11, pede truco
        assert res['ok'] is False
        assert res['jogo_encerrado'] is True
        assert res['dupla_vencedora_jogo'] == 1


class TestJogoCorrerMao11:
    def test_correr_mao_de_11(self):
        j = _criar_jogo_normal()
        j.placar[0] = 11
        j.iniciar_mao()
        res = j.correr_mao_de_11('Ana')
        assert res['ok'] is True
        assert j.placar[1] == 1

    def test_so_dupla_com_11_pode_correr(self):
        j = _criar_jogo_normal()
        j.placar[0] = 11
        j.iniciar_mao()
        res = j.correr_mao_de_11('Bob')  # Bob é dupla 1, não tem 11
        assert res['ok'] is False

    def test_correr_mao_de_11_nao_e_mao_de_11(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        res = j.correr_mao_de_11('Ana')
        assert res['ok'] is False


# ------------------------------------------------------------------ #
#  Serialização                                                       #
# ------------------------------------------------------------------ #

class TestSerializacao:
    def test_para_dict_e_de_dict(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        j.jogar_carta(j.jogador_da_vez(), 0)

        d = j.para_dict()
        j2 = Jogo.de_dict(d)

        assert j2.sala_id == j.sala_id
        assert j2.jogadores == j.jogadores
        assert j2.placar == j.placar
        assert j2.status == j.status
        assert j2.vez == j.vez
        assert j2.valor_mao == j.valor_mao
        assert j2.vira == j.vira

    def test_serializa_truco_pendente(self):
        j = _criar_jogo_normal()
        j.iniciar_mao()
        j.pedir_truco('Ana')

        d = j.para_dict()
        j2 = Jogo.de_dict(d)

        assert j2.status == 'truco_pendente'
        assert j2.valor_proposto == 3
        assert j2.dupla_pediu_truco == 0
