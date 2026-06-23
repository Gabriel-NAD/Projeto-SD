import random

# Ordem das cartas do menor para o maior valor
ORDEM_CARTAS = ['4', '5', '6', '7', 'Q', 'J', 'K', '1', '2', '3']

# Naipes e força para desempate de manilhas (maior para menor)
NAIPES = ['♣', '♥', '♠', '♦']
FORCA_NAIPE = {'♣': 4, '♥': 3, '♠': 2, '♦': 1}

# Sequência de valores possíveis para a mão
VALORES_MAO = [1, 3, 6, 9, 12]
PONTOS_MAXIMOS = 12


def criar_baralho():
    # Baralho francês sem 8, 9, 10 e coringa: 10 valores x 4 naipes = 40 cartas
    baralho = [(v, n) for v in ORDEM_CARTAS for n in NAIPES]
    random.shuffle(baralho)
    return baralho


def carta_str(carta):
    return carta[0] + carta[1]


def determinar_manilhas(vira):
    # Manilha é a carta seguinte à vira na ordem do truco
    idx = ORDEM_CARTAS.index(vira[0])
    valor_manilha = ORDEM_CARTAS[(idx + 1) % len(ORDEM_CARTAS)]
    return [(valor_manilha, naipe) for naipe in NAIPES]


def forca_carta(carta, manilhas):
    valor, naipe = carta
    # Manilhas têm força máxima, ordenadas por naipe
    for m in manilhas:
        if m[0] == valor and m[1] == naipe:
            return 100 + FORCA_NAIPE[naipe]
    return ORDEM_CARTAS.index(valor)


def proximo_valor_truco(valor_atual):
    idx = VALORES_MAO.index(valor_atual)
    if idx + 1 < len(VALORES_MAO):
        return VALORES_MAO[idx + 1]
    return None


def vencedor_rodada(jogadas, manilhas):
    """
    jogadas: lista de (nome, carta) — carta=None significa coberta (vale -1).
    Retorna nome do vencedor ou None em caso de empate.
    """
    melhor_nome = None
    melhor_forca = -1
    empate = False

    for nome, carta in jogadas:
        forca = forca_carta(carta, manilhas) if carta is not None else -1
        if forca > melhor_forca:
            melhor_forca = forca
            melhor_nome = nome
            empate = False
        elif forca == melhor_forca and melhor_forca >= 0:
            empate = True

    return None if empate else melhor_nome


def vencedor_mao(resultados, duplas):
    """
    resultados: lista de até 3 nomes vencedores de rodada (ou None = empate).
    duplas: dict nome -> id_dupla (0 ou 1).
    Retorna id_dupla vencedora ou None se mão não terminou ou empatou totalmente.
    """
    vitorias = {0: 0, 1: 0}
    primeira_dupla = None

    for i, v in enumerate(resultados):
        if v is not None:
            d = duplas[v]
            vitorias[d] += 1
            if i == 0:
                primeira_dupla = d

    # Dupla que venceu 2 rodadas leva a mão
    for d, v in vitorias.items():
        if v >= 2:
            return d

    n = len(resultados)
    r1 = resultados[0] if n >= 1 else None
    r2 = resultados[1] if n >= 2 else None

    if n == 2:
        if r1 is None and r2 is not None:
            # 1a empatou, 2a tem vencedor → vencedor da 2a leva
            return duplas[r2]
        if r1 is not None and r2 is None:
            # 1a tem vencedor, 2a empatou → vencedor da 1a leva
            return duplas[r1]
        # 1-1 ou ambas empataram → precisa de 3a rodada
        return None

    if n == 3:
        r3 = resultados[2]
        if r3 is not None:
            # 3a tem vencedor → esse time leva
            return duplas[r3]
        # 3a empatou: quem ganhou a 1a leva (ou 2a se 1a empatou, ou ninguém)
        if r1 is not None:
            return duplas[r1]
        if r2 is not None:
            return duplas[r2]
        return None  # todas empataram

    return None


class Jogo:
    def __init__(self, sala_id, jogadores, tipo='normal'):
        """
        jogadores: lista de nomes em ordem de jogo.
        tipo: 'normal' (4 jogadores, 2 duplas) ou '1v1' (2 jogadores).
        Duplas normais: índices 0,2 = dupla 0 | índices 1,3 = dupla 1.
        """
        self.sala_id = sala_id
        self.tipo = tipo
        self.jogadores = jogadores

        self.duplas = {}
        if tipo == 'normal':
            for i, nome in enumerate(jogadores):
                self.duplas[nome] = i % 2
        else:
            self.duplas = {jogadores[0]: 0, jogadores[1]: 1}

        self.placar = {0: 0, 1: 0}
        self.status = 'aguardando'

        # Estado da mão atual
        self.baralho = []
        self.maos = {}
        self.vira = None
        self.manilhas = []
        self.valor_mao = 1
        self.valor_proposto = None      # valor proposto pelo truco pendente
        self.dupla_pediu_truco = None   # dupla que fez o último pedido de truco
        self.resultados_rodadas = []    # vencedor (nome) de cada rodada ou None
        self.rodada_atual = []          # [(nome, carta)] jogadas da rodada em curso
        self.vez = 0                    # índice em self.jogadores de quem deve jogar
        self.primeiro_da_mao = 0        # índice de quem começa a mão
        self.mao_numero = 0

    # ------------------------------------------------------------------ #
    #  Início de mão                                                       #
    # ------------------------------------------------------------------ #

    def iniciar_mao(self):
        self.baralho = criar_baralho()
        self.maos = {}
        for nome in self.jogadores:
            self.maos[nome] = [self.baralho.pop() for _ in range(3)]
        self.vira = self.baralho.pop()
        self.manilhas = determinar_manilhas(self.vira)
        self.resultados_rodadas = []
        self.rodada_atual = []
        self.dupla_pediu_truco = None
        self.valor_proposto = None
        self.vez = self.primeiro_da_mao
        self.mao_numero += 1

        if self.eh_mao_de_ferro() or self.eh_mao_de_11():
            self.valor_mao = 3
        else:
            self.valor_mao = 1

        self.status = 'jogando'

    def eh_mao_de_11(self):
        return 11 in self.placar.values() and not self.eh_mao_de_ferro()

    def eh_mao_de_ferro(self):
        return self.placar[0] == 11 and self.placar[1] == 11

    def jogador_da_vez(self):
        return self.jogadores[self.vez]

    # ------------------------------------------------------------------ #
    #  Jogar carta                                                         #
    # ------------------------------------------------------------------ #

    def jogar_carta(self, nome, indice, coberta=False):
        if self.status != 'jogando':
            return {'ok': False, 'erro': 'Não é hora de jogar carta'}
        if nome != self.jogador_da_vez():
            return {'ok': False, 'erro': 'Não é sua vez'}
        if indice < 0 or indice >= len(self.maos[nome]):
            return {'ok': False, 'erro': 'Índice de carta inválido'}

        carta = self.maos[nome].pop(indice)
        carta_jogada = None if coberta else carta

        self.rodada_atual.append((nome, carta_jogada))
        self.vez = (self.vez + 1) % len(self.jogadores)

        resultado = {'ok': True, 'carta': carta_str(carta), 'coberta': coberta}

        if len(self.rodada_atual) == len(self.jogadores):
            resultado.update(self._encerrar_rodada())

        return resultado

    def _encerrar_rodada(self):
        vencedor = vencedor_rodada(self.rodada_atual, self.manilhas)
        self.resultados_rodadas.append(vencedor)
        self.rodada_atual = []

        resultado = {
            'rodada_encerrada': True,
            'vencedor_rodada': vencedor,
        }

        dupla_v = self.duplas[vencedor] if vencedor else None
        vencedor_m = vencedor_mao(self.resultados_rodadas, self.duplas)

        if vencedor_m is not None or len(self.resultados_rodadas) == 3:
            resultado.update(self._encerrar_mao(vencedor_m))
        else:
            # Próxima rodada começa pelo vencedor da rodada (ou mantém sequência no empate)
            if vencedor:
                self.vez = self.jogadores.index(vencedor)

        return resultado

    def _encerrar_mao(self, dupla_vencedora):
        pontos = self.valor_mao if dupla_vencedora is not None else 0
        if dupla_vencedora is not None:
            self.placar[dupla_vencedora] += pontos

        self.primeiro_da_mao = (self.primeiro_da_mao + 1) % len(self.jogadores)

        resultado = {
            'mao_encerrada': True,
            'dupla_vencedora_mao': dupla_vencedora,
            'pontos_ganhos': pontos,
            'placar': dict(self.placar),
        }

        for d, pts in self.placar.items():
            if pts >= PONTOS_MAXIMOS:
                self.status = 'encerrado'
                resultado['jogo_encerrado'] = True
                resultado['dupla_vencedora_jogo'] = d
                return resultado

        self.status = 'aguardando'
        return resultado

    # ------------------------------------------------------------------ #
    #  Truco                                                               #
    # ------------------------------------------------------------------ #

    def pedir_truco(self, nome):
        if self.status != 'jogando':
            return {'ok': False, 'erro': 'Não é possível pedir truco agora'}

        dupla = self.duplas[nome]

        # Na mão de 11, pedir truco faz perder o jogo
        if self.eh_mao_de_11():
            adversario = 1 - dupla
            self.placar[adversario] = PONTOS_MAXIMOS
            self.status = 'encerrado'
            return {
                'ok': False,
                'erro': 'Não se pode pedir truco na mão de 11',
                'jogo_encerrado': True,
                'dupla_vencedora_jogo': adversario,
            }

        if self.dupla_pediu_truco == dupla:
            return {'ok': False, 'erro': 'Sua dupla já fez o último pedido'}

        proximo = proximo_valor_truco(self.valor_mao)
        if proximo is None:
            return {'ok': False, 'erro': 'Mão já está no valor máximo (12)'}

        self.valor_proposto = proximo
        self.dupla_pediu_truco = dupla
        self.status = 'truco_pendente'
        return {'ok': True, 'valor_proposto': proximo, 'pedido_por': dupla}

    def responder_truco(self, nome, resposta):
        """resposta: 'aceitar' | 'correr' | 'aumentar'"""
        if self.status != 'truco_pendente':
            return {'ok': False, 'erro': 'Não há truco pendente'}

        dupla = self.duplas[nome]
        if dupla == self.dupla_pediu_truco:
            return {'ok': False, 'erro': 'Sua dupla fez o pedido, não pode responder'}

        if resposta == 'aceitar':
            self.valor_mao = self.valor_proposto
            self.valor_proposto = None
            self.status = 'jogando'
            return {'ok': True, 'acao': 'aceitar', 'valor_mao': self.valor_mao}

        elif resposta == 'correr':
            # Quem correu dá os pontos ATUAIS (não o proposto) para quem pediu.
            # _encerrar_mao já soma os pontos ao placar, não somar aqui.
            resultado = {'ok': True, 'acao': 'correr', 'pontos': self.valor_mao}
            self.valor_proposto = None
            resultado.update(self._encerrar_mao(self.dupla_pediu_truco))
            return resultado

        elif resposta == 'aumentar':
            # Aceita o valor proposto e faz contra-proposta com o próximo
            proximo_do_proximo = proximo_valor_truco(self.valor_proposto)
            if proximo_do_proximo is None:
                return {'ok': False, 'erro': 'Não é possível aumentar além de 12'}
            self.valor_mao = self.valor_proposto   # aceita o atual
            self.valor_proposto = proximo_do_proximo
            self.dupla_pediu_truco = dupla
            # status permanece 'truco_pendente'
            return {
                'ok': True,
                'acao': 'aumentar',
                'valor_mao': self.valor_mao,
                'valor_proposto': self.valor_proposto,
                'pedido_por': dupla,
            }

        return {'ok': False, 'erro': 'Resposta inválida'}

    # ------------------------------------------------------------------ #
    #  Correr na mão de 11                                                 #
    # ------------------------------------------------------------------ #

    def correr_mao_de_11(self, nome):
        """Só a dupla com 11 pontos pode correr antes da mão começar."""
        if not self.eh_mao_de_11():
            return {'ok': False, 'erro': 'Não é mão de 11'}
        dupla = self.duplas[nome]
        dupla_com_11 = next(d for d, p in self.placar.items() if p == 11)
        if dupla != dupla_com_11:
            return {'ok': False, 'erro': 'Só a dupla com 11 pontos pode correr'}

        adversario = 1 - dupla
        self.placar[adversario] += 1
        resultado = {'ok': True, 'pontos_adversario': 1, 'placar': dict(self.placar)}

        if self.placar[adversario] >= PONTOS_MAXIMOS:
            self.status = 'encerrado'
            resultado['jogo_encerrado'] = True
            resultado['dupla_vencedora_jogo'] = adversario
        else:
            self.status = 'aguardando'
            resultado['mao_encerrada'] = True

        return resultado

    # ------------------------------------------------------------------ #
    #  Serialização para Redis                                             #
    # ------------------------------------------------------------------ #

    def para_dict(self):
        return {
            'sala_id': self.sala_id,
            'tipo': self.tipo,
            'jogadores': self.jogadores,
            'duplas': self.duplas,
            'placar': {str(k): v for k, v in self.placar.items()},
            'status': self.status,
            'maos': {nome: [list(c) for c in cartas] for nome, cartas in self.maos.items()},
            'vira': list(self.vira) if self.vira else None,
            'manilhas': [list(m) for m in self.manilhas],
            'valor_mao': self.valor_mao,
            'valor_proposto': self.valor_proposto,
            'dupla_pediu_truco': self.dupla_pediu_truco,
            'resultados_rodadas': self.resultados_rodadas,
            'rodada_atual': [(n, list(c) if c else None) for n, c in self.rodada_atual],
            'vez': self.vez,
            'primeiro_da_mao': self.primeiro_da_mao,
            'mao_numero': self.mao_numero,
        }

    @classmethod
    def de_dict(cls, d):
        jogo = cls.__new__(cls)
        jogo.sala_id = d['sala_id']
        jogo.tipo = d['tipo']
        jogo.jogadores = d['jogadores']
        jogo.duplas = {k: int(v) for k, v in d['duplas'].items()}
        jogo.placar = {int(k): v for k, v in d['placar'].items()}
        jogo.status = d['status']
        jogo.maos = {
            nome: [tuple(c) for c in cartas]
            for nome, cartas in d['maos'].items()
        }
        jogo.vira = tuple(d['vira']) if d['vira'] else None
        jogo.manilhas = [tuple(m) for m in d['manilhas']]
        jogo.valor_mao = d['valor_mao']
        jogo.valor_proposto = d['valor_proposto']
        jogo.dupla_pediu_truco = d['dupla_pediu_truco']
        jogo.resultados_rodadas = d['resultados_rodadas']
        jogo.rodada_atual = [
            (n, tuple(c) if c else None) for n, c in d['rodada_atual']
        ]
        jogo.vez = d['vez']
        jogo.primeiro_da_mao = d['primeiro_da_mao']
        jogo.mao_numero = d['mao_numero']
        return jogo
