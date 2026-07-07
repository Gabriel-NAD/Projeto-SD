import pygame
import os
import time

from cliente import Cliente, BROKER_HOST, BROKER_PORT

# ------------------------------------------------------------------ #
#  Configurações da janela                                             #
# ------------------------------------------------------------------ #

LARGURA = 1280
ALTURA  = 720
FPS     = 30

# Cores (R, G, B)
VERDE_MESA   = (24, 98, 58)
VERDE_TOPO   = (32, 116, 70)    # topo do gradiente do fundo
VERDE_BASE   = (13, 56, 34)     # base do gradiente do fundo
VERDE_ESCURO = (14, 62, 38)
CINZA_PAINEL = (38, 42, 48)
CINZA_CAMPO  = (58, 62, 70)
CINZA_CLARO  = (150, 155, 160)
BRANCO       = (240, 240, 240)
AMARELO      = (255, 210, 80)
DOURADO      = (212, 175, 90)
VERMELHO     = (225, 90, 90)
VERDE_OK     = (110, 200, 120)
AZUL_BOTAO   = (52, 110, 180)
AZUL_HOVER   = (76, 140, 215)
LARANJA      = (230, 150, 60)

# Tamanhos das cartas (proporção 500x726 dos sprites)
CARTA_MAO   = (100, 145)   # cartas na mão do jogador
CARTA_MESA  = (90, 131)    # cartas jogadas na mesa
CARTA_MINI  = (54, 78)     # cartas dos outros jogadores / vira

# Preenchidos em inicializar()
FONTES  = {}
CARTAS  = {}   # tamanho -> {arquivo: Surface}
FUNDO   = None # Surface com o gradiente da mesa


# ------------------------------------------------------------------ #
#  Sprites das cartas                                                 #
# ------------------------------------------------------------------ #

NOMES_VALOR = {'1': 'ace', 'Q': 'queen', 'J': 'jack', 'K': 'king'}
NOMES_NAIPE = {'♣': 'clubs', '♥': 'hearts', '♠': 'spades', '♦': 'diamonds'}


def arquivo_carta(carta):
    """Converte a carta do protocolo ('7♥', '1♣', '????') no nome do sprite."""
    if not carta or carta == '????':
        return 'back.png'
    valor, naipe = carta[0], carta[1:]
    v = NOMES_VALOR.get(valor, valor)
    n = NOMES_NAIPE.get(naipe)
    if n is None:
        return 'back.png'
    return f'{v}_of_{n}.png'


def carregar_cartas():
    """Carrega os sprites (baralho Atlas, CC0) nas três escalas da interface."""
    pasta = os.path.join(os.path.dirname(__file__), 'assets', 'cartas')
    originais = {}
    for arq in os.listdir(pasta):
        if arq.endswith('.png'):
            originais[arq] = pygame.image.load(os.path.join(pasta, arq)).convert_alpha()

    for nome, tamanho in (('mao', CARTA_MAO), ('mesa', CARTA_MESA), ('mini', CARTA_MINI)):
        CARTAS[nome] = {
            arq: pygame.transform.smoothscale(img, tamanho)
            for arq, img in originais.items()
        }


def _criar_fundo():
    """Gradiente vertical de verde com vinheta nas bordas (feltro de mesa)."""
    fundo = pygame.Surface((LARGURA, ALTURA))
    for y in range(ALTURA):
        t = y / ALTURA
        cor = tuple(int(VERDE_TOPO[i] + (VERDE_BASE[i] - VERDE_TOPO[i]) * t)
                    for i in range(3))
        pygame.draw.line(fundo, cor, (0, y), (LARGURA, y))
    # Vinheta: laterais levemente mais escuras
    sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for i in range(120):
        alfa = int(60 * (1 - i / 120))
        pygame.draw.rect(sombra, (0, 0, 0, alfa), (i, i, LARGURA - 2 * i, ALTURA - 2 * i), width=1)
    fundo.blit(sombra, (0, 0))
    return fundo


def inicializar():
    global FUNDO
    pygame.init()
    janela = pygame.display.set_mode((LARGURA, ALTURA))
    pygame.display.set_caption('Truco Paulista')

    # DejaVu (Linux) e Arial (Windows) têm os símbolos de naipe
    nome_fonte = 'dejavusans,arial,helvetica'
    FONTES['titulo']  = pygame.font.SysFont(nome_fonte, 44, bold=True)
    FONTES['grande']  = pygame.font.SysFont(nome_fonte, 28, bold=True)
    FONTES['normal']  = pygame.font.SysFont(nome_fonte, 22)
    FONTES['pequena'] = pygame.font.SysFont(nome_fonte, 17)

    carregar_cartas()
    FUNDO = _criar_fundo()
    return janela


# ------------------------------------------------------------------ #
#  Helpers de desenho                                                 #
# ------------------------------------------------------------------ #

def texto(janela, msg, x, y, fonte='normal', cor=BRANCO, centro=False, sombra=False):
    if sombra:
        surf_s = FONTES[fonte].render(str(msg), True, (0, 0, 0))
        rect_s = surf_s.get_rect()
        if centro:
            rect_s.center = (x + 2, y + 3)
        else:
            rect_s.topleft = (x + 2, y + 3)
        surf_s.set_alpha(130)
        janela.blit(surf_s, rect_s)
    surf = FONTES[fonte].render(str(msg), True, cor)
    rect = surf.get_rect()
    if centro:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    janela.blit(surf, rect)
    return rect


def desenhar_carta(janela, escala, carta, x, y):
    """Desenha uma carta com sombra projetada."""
    img = CARTAS[escala][arquivo_carta(carta)]
    larg, alt = img.get_size()
    sombra = pygame.Surface((larg, alt), pygame.SRCALPHA)
    pygame.draw.rect(sombra, (0, 0, 0, 90), (0, 0, larg, alt),
                     border_radius=max(5, larg // 12))
    janela.blit(sombra, (x + 3, y + 4))
    janela.blit(img, (x, y))


def quebrar_texto(msg, fonte, largura_max):
    """Quebra uma mensagem em linhas que caibam na largura dada."""
    palavras = str(msg).split(' ')
    linhas, atual = [], ''
    for p in palavras:
        tentativa = (atual + ' ' + p).strip()
        if FONTES[fonte].size(tentativa)[0] <= largura_max:
            atual = tentativa
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


class Botao:
    def __init__(self, rotulo, x, y, larg, alt, cor=AZUL_BOTAO):
        self.rotulo = rotulo
        self.rect = pygame.Rect(x, y, larg, alt)
        self.cor = cor

    def desenhar(self, janela, fonte='normal'):
        hover = self.rect.collidepoint(pygame.mouse.get_pos())
        cor = self.cor
        if hover:
            cor = tuple(min(255, c + 28) for c in self.cor)
        sombra = self.rect.move(0, 3)
        s = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 90), s.get_rect(), border_radius=10)
        janela.blit(s, sombra.topleft)
        pygame.draw.rect(janela, cor, self.rect, border_radius=10)
        pygame.draw.rect(janela, tuple(min(255, c + 45) for c in cor),
                         self.rect, width=1, border_radius=10)
        texto(janela, self.rotulo, self.rect.centerx, self.rect.centery,
              fonte=fonte, centro=True)

    def clicou(self, pos):
        return self.rect.collidepoint(pos)


class CampoTexto:
    def __init__(self, x, y, larg, alt, ocultar=False, max_len=50):
        self.rect = pygame.Rect(x, y, larg, alt)
        self.texto = ''
        self.ativo = False
        self.ocultar = ocultar
        self.max_len = max_len

    def tratar_evento(self, ev):
        """Retorna True quando ENTER é pressionado com o campo ativo."""
        if ev.type == pygame.MOUSEBUTTONDOWN:
            self.ativo = self.rect.collidepoint(ev.pos)
        elif ev.type == pygame.KEYDOWN and self.ativo:
            if ev.key == pygame.K_RETURN:
                return True
            elif ev.key == pygame.K_BACKSPACE:
                self.texto = self.texto[:-1]
            elif ev.unicode and ev.unicode.isprintable() and len(self.texto) < self.max_len:
                self.texto += ev.unicode
        return False

    def desenhar(self, janela):
        cor_borda = AMARELO if self.ativo else CINZA_CLARO
        pygame.draw.rect(janela, CINZA_CAMPO, self.rect, border_radius=6)
        pygame.draw.rect(janela, cor_borda, self.rect, width=2, border_radius=6)
        exibido = '*' * len(self.texto) if self.ocultar else self.texto
        if self.ativo and int(time.time() * 2) % 2 == 0:
            exibido += '|'
        texto(janela, exibido, self.rect.x + 10, self.rect.y + 8)


def desenhar_fundo(janela, titulo=None):
    janela.blit(FUNDO, (0, 0))
    if titulo:
        pygame.draw.rect(janela, VERDE_ESCURO, (0, 0, LARGURA, 64))
        pygame.draw.line(janela, DOURADO, (0, 64), (LARGURA, 64), 2)
        texto(janela, titulo, LARGURA // 2, 32, fonte='titulo', cor=AMARELO,
              centro=True, sombra=True)


def desenhar_status(janela, cliente, y=ALTURA - 30):
    if cliente.status_msg:
        cor = VERMELHO if '[ERRO]' in cliente.status_msg else AMARELO
        texto(janela, cliente.status_msg, LARGURA // 2, y, cor=cor, centro=True)


def eventos_basicos(campos=()):
    """Processa QUIT e eventos dos campos; retorna (continuar, clique, enter)."""
    clique = None
    enter = False
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            return False, None, False
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            clique = ev.pos
        for campo in campos:
            if campo.tratar_evento(ev):
                enter = True
    return True, clique, enter


# ------------------------------------------------------------------ #
#  Tela: início                                                       #
# ------------------------------------------------------------------ #

def tela_inicio(janela, cliente):
    relogio = pygame.time.Clock()
    cx = LARGURA // 2 - 130
    b_login    = Botao('Login', cx, 300, 260, 52)
    b_cadastro = Botao('Cadastro', cx, 370, 260, 52)
    b_sair     = Botao('Sair', cx, 440, 260, 52, cor=VERMELHO)

    while cliente.tela == 'inicio':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False

        if clique:
            if b_login.clicou(clique):
                cliente.tela = 'login'
            elif b_cadastro.clicou(clique):
                cliente.tela = 'cadastro'
            elif b_sair.clicou(clique):
                return False

        desenhar_fundo(janela)
        # Leque decorativo de cartas atrás do título
        for carta, angulo, dx in (('1♠', 18, -90), ('7♥', 0, 0), ('3♣', -18, 90)):
            img = pygame.transform.rotate(CARTAS['mao'][arquivo_carta(carta)], angulo)
            rect = img.get_rect(center=(LARGURA // 2 + dx, 120))
            janela.blit(img, rect)
        texto(janela, 'TRUCO PAULISTA', LARGURA // 2, 230, fonte='titulo',
              cor=AMARELO, centro=True, sombra=True)
        texto(janela, 'Jogo de cartas distribuido', LARGURA // 2, 275, centro=True)
        for b in (b_login, b_cadastro, b_sair):
            b.desenhar(janela)
        desenhar_status(janela, cliente)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Telas: login e cadastro                                            #
# ------------------------------------------------------------------ #

def tela_formulario(janela, cliente, modo):
    """Tela de login ou cadastro (modo = 'login' | 'cadastro')."""
    relogio = pygame.time.Clock()
    cx = LARGURA // 2 - 180
    campo_nome  = CampoTexto(cx, 280, 360, 42)
    campo_senha = CampoTexto(cx, 370, 360, 42, ocultar=True)
    campo_nome.ativo = True
    rotulo = 'Entrar' if modo == 'login' else 'Cadastrar'
    b_ok     = Botao(rotulo, cx, 450, 170, 48)
    b_voltar = Botao('Voltar', cx + 190, 450, 170, 48, cor=CINZA_CAMPO)
    aguardando_desde = None

    while cliente.tela == modo:
        cliente.processar_fila()

        # Login bem-sucedido muda a tela para 'lobby' sozinho (token no ok)
        if modo == 'cadastro' and 'realizado' in cliente.status_msg.lower():
            cliente.tela = 'inicio'
            break

        continuar, clique, enter = eventos_basicos(campos=(campo_nome, campo_senha))
        if not continuar:
            return False

        # TAB ou ENTER no nome pula para a senha
        if enter and campo_nome.ativo and not campo_senha.texto:
            campo_nome.ativo, campo_senha.ativo = False, True
            enter = False

        submeter = enter or (clique and b_ok.clicou(clique))
        if clique and b_voltar.clicou(clique):
            cliente.status_msg = ''
            cliente.tela = 'inicio'
            break

        if submeter and campo_nome.texto.strip() and campo_senha.texto.strip():
            nome, senha = campo_nome.texto.strip(), campo_senha.texto.strip()
            cliente.status_msg = ''
            if modo == 'login':
                cliente.nome  = nome
                cliente.senha = senha
                cliente.enviar({'tipo': 'login', 'nome': nome, 'senha': senha})
            else:
                cliente.enviar({'tipo': 'registro', 'nome': nome, 'senha': senha})
            aguardando_desde = time.time()

        if aguardando_desde and time.time() - aguardando_desde > 5:
            if not cliente.status_msg:
                cliente.status_msg = '[ERRO] Servidor nao respondeu'
            aguardando_desde = None

        desenhar_fundo(janela, titulo='LOGIN' if modo == 'login' else 'CADASTRO')
        texto(janela, 'Nome de usuario:', cx, 250)
        campo_nome.desenhar(janela)
        texto(janela, 'Senha:', cx, 340)
        campo_senha.desenhar(janela)
        b_ok.desenhar(janela)
        b_voltar.desenhar(janela)
        if aguardando_desde:
            texto(janela, 'Aguardando...', LARGURA // 2, 530, cor=AMARELO, centro=True)
        desenhar_status(janela, cliente, y=560)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Tela: lobby                                                        #
# ------------------------------------------------------------------ #

def tela_lobby(janela, cliente):
    relogio = pygame.time.Clock()
    cx = LARGURA // 2 - 130
    b_salas   = Botao('Ver Salas', cx, 280, 260, 52)
    b_perfil  = Botao('Meu Perfil', cx, 350, 260, 52)
    b_ranking = Botao('Ranking Global', cx, 420, 260, 52)
    b_sair    = Botao('Sair', cx, 490, 260, 52, cor=VERMELHO)

    while cliente.tela == 'lobby':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False

        if clique:
            if b_salas.clicou(clique):
                cliente.enviar({'tipo': 'listar_salas'})
                cliente.tela = 'aguardando'
            elif b_perfil.clicou(clique):
                cliente.enviar({'tipo': 'meu_perfil'})
                cliente.tela = 'aguardando'
            elif b_ranking.clicou(clique):
                cliente.enviar({'tipo': 'ranking'})
                cliente.tela = 'aguardando'
            elif b_sair.clicou(clique):
                return False

        desenhar_fundo(janela, titulo='LOBBY')
        texto(janela, f'Bem-vindo, {cliente.nome}!', LARGURA // 2, 180,
              fonte='grande', centro=True)
        for b in (b_salas, b_perfil, b_ranking, b_sair):
            b.desenhar(janela)
        desenhar_status(janela, cliente)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


def tela_aguardando(janela, cliente):
    relogio = pygame.time.Clock()
    inicio = time.time()
    while cliente.tela == 'aguardando':
        cliente.processar_fila()
        continuar, _, _ = eventos_basicos()
        if not continuar:
            return False
        if time.time() - inicio > 5:
            cliente.tela = 'lobby'
            break
        desenhar_fundo(janela)
        texto(janela, 'Aguardando servidor...', LARGURA // 2, ALTURA // 2,
              fonte='grande', centro=True)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Tela: lista de salas                                               #
# ------------------------------------------------------------------ #

def tela_salas(janela, cliente):
    relogio = pygame.time.Clock()
    b_atualizar = Botao('Atualizar', LARGURA - 400, ALTURA - 70, 180, 46)
    b_voltar    = Botao('Voltar', LARGURA - 200, ALTURA - 70, 160, 46, cor=CINZA_CAMPO)

    while cliente.tela == 'salas':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False

        # Duas colunas de 8 salas
        retangulos = []
        for i, sala in enumerate(cliente.lista_salas):
            col, lin = i // 8, i % 8
            x = 90 + col * 570
            y = 100 + lin * 66
            retangulos.append((pygame.Rect(x, y, 530, 56), sala))

        if clique:
            if b_voltar.clicou(clique):
                cliente.tela = 'lobby'
                break
            if b_atualizar.clicou(clique):
                cliente.enviar({'tipo': 'listar_salas'})
            for rect, sala in retangulos:
                if rect.collidepoint(clique) and sala.get('status') != 'jogando':
                    cliente.status_msg = ''
                    cliente.chat_msgs  = []   # chat começa limpo a cada partida
                    cliente.enviar({'tipo': 'entrar_sala', 'sala': sala['id']})
                    cliente.sala_id = sala['id']
                    # Aguarda resposta: estado_jogo (jogo), ok (espera) ou erro
                    inicio = time.time()
                    while time.time() - inicio < 5:
                        cliente.processar_fila()
                        if cliente.tela != 'salas' or '[ERRO]' in cliente.status_msg:
                            break
                        if cliente.status_msg:
                            cliente.tela = 'espera_sala'
                            break
                        time.sleep(0.05)
                    break

        if cliente.tela != 'salas':
            break

        desenhar_fundo(janela, titulo='SALAS')
        for rect, sala in retangulos:
            jogando = sala.get('status') == 'jogando'
            hover = rect.collidepoint(pygame.mouse.get_pos()) and not jogando
            cor = CINZA_CAMPO if jogando else (AZUL_HOVER if hover else CINZA_PAINEL)
            pygame.draw.rect(janela, cor, rect, border_radius=8)
            tipo = '1v1' if sala.get('tipo') == '1v1' else 'normal'
            texto(janela, f"Sala {sala.get('id')}  ({tipo})", rect.x + 16, rect.y + 15)
            texto(janela, f"{sala.get('jogadores')}/{sala.get('max')}",
                  rect.x + 330, rect.y + 15, cor=AMARELO)
            cor_st = CINZA_CLARO if jogando else VERDE_OK
            texto(janela, sala.get('status', ''), rect.x + 400, rect.y + 15, cor=cor_st)
        b_atualizar.desenhar(janela)
        b_voltar.desenhar(janela)
        desenhar_status(janela, cliente, y=ALTURA - 100)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Chat (painel compartilhado entre espera e jogo)                    #
# ------------------------------------------------------------------ #

def desenhar_chat(janela, cliente, campo_chat, x, y, larg, alt):
    pygame.draw.rect(janela, CINZA_PAINEL, (x, y, larg, alt), border_radius=10)
    pygame.draw.rect(janela, (70, 76, 84), (x, y, larg, alt), width=1, border_radius=10)
    pygame.draw.rect(janela, (28, 31, 36), (x, y, larg, 30),
                     border_top_left_radius=10, border_top_right_radius=10)
    texto(janela, 'CHAT', x + 12, y + 6, fonte='pequena', cor=AMARELO)

    # Junta as mensagens quebradas em linhas e mostra as últimas
    linhas = []
    for msg in cliente.chat_msgs:
        cor = CINZA_CLARO if msg.startswith('>>>') else BRANCO
        for l in quebrar_texto(msg, 'pequena', larg - 24):
            linhas.append((l, cor))
    altura_linha = 22
    max_linhas = (alt - 80) // altura_linha
    for i, (l, cor) in enumerate(linhas[-max_linhas:]):
        texto(janela, l, x + 12, y + 34 + i * altura_linha, fonte='pequena', cor=cor)

    campo_chat.rect.topleft = (x + 8, y + alt - 44)
    campo_chat.rect.size = (larg - 16, 36)
    campo_chat.desenhar(janela)


def enviar_chat(cliente, campo_chat):
    msg = campo_chat.texto.strip()
    if msg:
        cliente.enviar({'tipo': 'chat', 'mensagem': msg})
    campo_chat.texto = ''


# ------------------------------------------------------------------ #
#  Tela: espera na sala                                               #
# ------------------------------------------------------------------ #

def tela_espera_sala(janela, cliente):
    relogio = pygame.time.Clock()
    campo_chat = CampoTexto(0, 0, 100, 36, max_len=100)
    b_sair = Botao('Sair da sala', 90, ALTURA - 70, 200, 46, cor=VERMELHO)

    while cliente.tela == 'espera_sala':
        cliente.processar_fila()
        continuar, clique, enter = eventos_basicos(campos=(campo_chat,))
        if not continuar:
            return False
        if enter:
            enviar_chat(cliente, campo_chat)

        if clique and b_sair.clicou(clique):
            cliente.enviar({'tipo': 'sair_sala'})
            cliente.sala_id = None
            cliente.tela = 'lobby'
            break

        desenhar_fundo(janela, titulo=f'SALA {cliente.sala_id}')
        pontos = '.' * (int(time.time() * 2) % 4)
        texto(janela, f'Aguardando jogadores entrarem{pontos}', LARGURA // 2, 140,
              fonte='grande', centro=True)
        desenhar_chat(janela, cliente, campo_chat, 340, 200, 600, 420)
        b_sair.desenhar(janela)
        desenhar_status(janela, cliente)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Telas: perfil e ranking                                            #
# ------------------------------------------------------------------ #

def tela_perfil(janela, cliente):
    relogio = pygame.time.Clock()
    b_voltar = Botao('Voltar', LARGURA // 2 - 90, 520, 180, 48)
    p = cliente.perfil or {}

    while cliente.tela == 'perfil':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False
        if clique and b_voltar.clicou(clique):
            cliente.tela = 'lobby'
            break

        desenhar_fundo(janela, titulo='MEU PERFIL')
        pygame.draw.rect(janela, CINZA_PAINEL, (LARGURA // 2 - 220, 160, 440, 310),
                         border_radius=10)
        linhas = [
            ('Nome',     p.get('nome', '-')),
            ('Partidas', p.get('partidas', 0)),
            ('Vitorias', p.get('vitorias', 0)),
            ('Derrotas', p.get('derrotas', 0)),
        ]
        for i, (rotulo, valor) in enumerate(linhas):
            y = 210 + i * 60
            texto(janela, rotulo + ':', LARGURA // 2 - 180, y, fonte='grande', cor=CINZA_CLARO)
            texto(janela, valor, LARGURA // 2 + 60, y, fonte='grande')
        b_voltar.desenhar(janela)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


def tela_ranking(janela, cliente):
    relogio = pygame.time.Clock()
    b_voltar = Botao('Voltar', LARGURA // 2 - 90, ALTURA - 70, 180, 48)

    while cliente.tela == 'ranking':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False
        if clique and b_voltar.clicou(clique):
            cliente.tela = 'lobby'
            break

        desenhar_fundo(janela, titulo='RANKING GLOBAL')
        pygame.draw.rect(janela, CINZA_PAINEL, (LARGURA // 2 - 300, 90, 600, 540),
                         border_radius=10)
        texto(janela, '#', LARGURA // 2 - 270, 105, cor=AMARELO)
        texto(janela, 'NOME', LARGURA // 2 - 200, 105, cor=AMARELO)
        texto(janela, 'VITORIAS', LARGURA // 2 + 150, 105, cor=AMARELO)
        for i, entry in enumerate(cliente.ranking_lista[:15]):
            y = 140 + i * 32
            cor = AMARELO if i == 0 else BRANCO
            texto(janela, i + 1, LARGURA // 2 - 270, y, cor=cor)
            texto(janela, entry.get('nome', '?'), LARGURA // 2 - 200, y, cor=cor)
            texto(janela, entry.get('vitorias', 0), LARGURA // 2 + 150, y, cor=cor)
        b_voltar.desenhar(janela)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Tela: jogo                                                         #
# ------------------------------------------------------------------ #

def _info_jogador(jogadores, nome):
    return next((j for j in jogadores if j['nome'] == nome), {})


def _desenhar_jogador_mini(janela, j, x, y):
    """Desenha as costas das cartas e o nome de um jogador (adversário/parceiro)."""
    # Moldura dourada em quem está na vez
    if j.get('vez'):
        n = max(1, j.get('n_cartas', 0))
        moldura = pygame.Rect(x - 8, y - 8, n * 24 + CARTA_MINI[0] - 24 + 16,
                              CARTA_MINI[1] + 58)
        pygame.draw.rect(janela, DOURADO, moldura, width=2, border_radius=10)
    for c in range(j.get('n_cartas', 0)):
        desenhar_carta(janela, 'mini', '????', x + c * 24, y)
    cor_nome = AMARELO if j.get('vez') else BRANCO
    texto(janela, j.get('nome', '?'), x, y + 84, fonte='pequena', cor=cor_nome)
    cor_st = VERDE_OK if j.get('online') else VERMELHO
    st = 'online' if j.get('online') else 'offline'
    texto(janela, st, x, y + 104, fonte='pequena', cor=cor_st)


def tela_jogo(janela, cliente):
    relogio = pygame.time.Clock()
    campo_chat = CampoTexto(0, 0, 100, 36, max_len=100)
    modo_coberta = False

    LARG_JOGO = 930   # área do jogo; o chat ocupa o resto à direita

    while cliente.tela == 'jogo':
        cliente.processar_fila()

        estado    = cliente.estado_jogo or {}
        jogadores = estado.get('jogadores', [])
        eu        = _info_jogador(jogadores, cliente.nome)
        minha_dupla    = eu.get('dupla')
        dupla_pediu    = estado.get('dupla_pediu_truco')
        status_jogo    = estado.get('status', 'jogando')
        mao_de_11      = estado.get('mao_de_11', False)
        minha_vez      = eu.get('vez', False)
        truco_pendente = (status_jogo == 'truco_pendente')
        devo_responder = truco_pendente and minha_dupla is not None and minha_dupla != dupla_pediu

        placar = estado.get('placar', [0, 0])
        dupla_com_11 = next((i for i, p in enumerate(placar) if p == 11), None)
        posso_correr_11 = mao_de_11 and (minha_dupla == dupla_com_11)
        pode_jogar = minha_vez and status_jogo == 'jogando'

        adversarios = [j for j in jogadores if j.get('dupla') != minha_dupla]
        parceiros   = [j for j in jogadores
                       if j.get('dupla') == minha_dupla and j.get('nome') != cliente.nome]
        suas_cartas = estado.get('suas_cartas', [])

        # Retângulos das cartas da mão (para clique e hover)
        n = len(suas_cartas)
        x0 = (LARG_JOGO - (n * (CARTA_MAO[0] + 14) - 14)) // 2 if n else 0
        rects_mao = [pygame.Rect(x0 + i * (CARTA_MAO[0] + 14), 505, *CARTA_MAO)
                     for i in range(n)]

        # Botões contextuais
        botoes = []
        by = ALTURA - 56
        if devo_responder:
            botoes = [
                (Botao('Aceitar', 20, by, 150, 44, cor=VERDE_ESCURO), 'aceitar'),
                (Botao('Retruco', 190, by, 150, 44, cor=LARANJA), 'aumentar'),
                (Botao('Correr', 360, by, 150, 44, cor=VERMELHO), 'correr'),
            ]
        elif pode_jogar or posso_correr_11:
            bx = 20
            if pode_jogar and not mao_de_11:
                rotulo = f"Coberta: {'SIM' if modo_coberta else 'NAO'}"
                botoes.append((Botao(rotulo, bx, by, 170, 44,
                                     cor=LARANJA if modo_coberta else CINZA_CAMPO), 'coberta'))
                bx += 190
                botoes.append((Botao('Truco!', bx, by, 130, 44, cor=LARANJA), 'truco'))
                bx += 150
                botoes.append((Botao('Correr', bx, by, 130, 44, cor=VERMELHO), 'correr_votar'))
                bx += 150
            if posso_correr_11:
                botoes.append((Botao('Correr (mao de 11)', bx, by, 220, 44, cor=VERMELHO),
                               'correr_11'))
        b_sair = Botao('Sair', LARG_JOGO - 110, by, 90, 44, cor=CINZA_CAMPO)

        continuar, clique, enter = eventos_basicos(campos=(campo_chat,))
        if not continuar:
            return False
        if enter:
            enviar_chat(cliente, campo_chat)

        if clique:
            if b_sair.clicou(clique):
                cliente.enviar({'tipo': 'sair_sala'})
                cliente.sala_id     = None
                cliente.estado_jogo = None
                cliente.tela        = 'lobby'
                break

            for botao, acao in botoes:
                if botao.clicou(clique):
                    if acao == 'aceitar':
                        cliente.enviar({'tipo': 'responder_truco', 'resposta': 'aceitar'})
                    elif acao == 'aumentar':
                        cliente.enviar({'tipo': 'responder_truco', 'resposta': 'aumentar'})
                    elif acao == 'correr':
                        cliente.enviar({'tipo': 'votar_correr', 'voto': True})
                    elif acao == 'truco':
                        cliente.enviar({'tipo': 'pedir_truco'})
                    elif acao == 'correr_votar':
                        cliente.enviar({'tipo': 'votar_correr', 'voto': True})
                    elif acao == 'correr_11':
                        cliente.enviar({'tipo': 'correr_mao_de_11'})
                    elif acao == 'coberta':
                        modo_coberta = not modo_coberta

            if pode_jogar:
                for i, rect in enumerate(rects_mao):
                    if rect.collidepoint(clique):
                        tipo = 'jogar_coberta' if modo_coberta else 'jogar_carta'
                        cliente.enviar({'tipo': tipo, 'indice': i})
                        cliente.status_msg = ''
                        modo_coberta = False
                        break

        # ---------------------------- desenho ----------------------------
        janela.blit(FUNDO, (0, 0))

        # Área central da mesa (feltro demarcado onde as cartas caem)
        mesa_rect = pygame.Rect(120, 240, LARG_JOGO - 240, 220)
        s = pygame.Surface(mesa_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (0, 0, 0, 45), s.get_rect(), border_radius=24)
        janela.blit(s, mesa_rect.topleft)
        pygame.draw.rect(janela, DOURADO, mesa_rect, width=2, border_radius=24)

        # Cabeçalho
        pygame.draw.rect(janela, VERDE_ESCURO, (0, 0, LARGURA, 48))
        pygame.draw.line(janela, DOURADO, (0, 48), (LARGURA, 48), 2)
        sala_str = f"Sala {estado.get('sala', '?')} ({estado.get('tipo', '?')})"
        info = (f"{sala_str}   Rodada {estado.get('rodada_atual', 1)}/3   "
                f"Mao vale {estado.get('mao_valor', 1)} pts")
        vp = estado.get('valor_proposto')
        if vp:
            info += f"   Truco: {vp} pts"
        texto(janela, info, 16, 12)
        lado_a = 'Voces' if minha_dupla == 0 else 'Eles'
        lado_b = 'Voces' if minha_dupla == 1 else 'Eles'
        texto(janela, f"{lado_a} {placar[0]}  x  {placar[1]} {lado_b}",
              LARG_JOGO - 20, 12, fonte='grande', cor=AMARELO, centro=False,
              sombra=True)

        # Adversários (em cima)
        texto(janela, 'ADVERSARIOS', 20, 60, fonte='pequena', cor=CINZA_CLARO)
        for i, j in enumerate(adversarios):
            _desenhar_jogador_mini(janela, j, 30 + i * 220, 84)

        # Vira e mesa (centro)
        if estado.get('vira'):
            texto(janela, 'Vira', 40, 250, fonte='pequena', cor=CINZA_CLARO)
            desenhar_carta(janela, 'mini', estado['vira'], 28, 272)
        if estado.get('mao_de_ferro'):
            texto(janela, 'MAO DE FERRO!', LARG_JOGO // 2, 218, fonte='grande',
                  cor=VERMELHO, centro=True, sombra=True)

        mesa = estado.get('mesa', [])
        n_mesa = len(mesa)
        mx0 = (LARG_JOGO - (n_mesa * (CARTA_MESA[0] + 30) - 30)) // 2 if n_mesa else 0
        for i, jogada in enumerate(mesa):
            x = mx0 + i * (CARTA_MESA[0] + 30)
            desenhar_carta(janela, 'mesa', jogada.get('carta'), x, 280)
            texto(janela, jogada.get('jogador', '?'), x + CARTA_MESA[0] // 2, 428,
                  fonte='pequena', centro=True)
        if not mesa:
            texto(janela, '(nenhuma carta na mesa)', LARG_JOGO // 2, 345,
                  cor=(190, 200, 190), centro=True)

        # Parceiro (à direita da área do jogo)
        if parceiros:
            texto(janela, 'SUA DUPLA', LARG_JOGO - 210, 60, fonte='pequena', cor=CINZA_CLARO)
            for i, j in enumerate(parceiros):
                _desenhar_jogador_mini(janela, j, LARG_JOGO - 200 + i * 160, 84)

        # Sua mão (embaixo)
        cor_voce = AMARELO if minha_vez else BRANCO
        texto(janela, f'Voce ({cliente.nome})' + ('  — SUA VEZ!' if minha_vez else ''),
              20, 475, cor=cor_voce, sombra=minha_vez)
        mouse = pygame.mouse.get_pos()
        for i, rect in enumerate(rects_mao):
            hover = pode_jogar and rect.collidepoint(mouse)
            y = rect.y - 18 if hover else rect.y
            desenhar_carta(janela, 'mao', suas_cartas[i], rect.x, y)
            if hover:
                pygame.draw.rect(janela, AMARELO, (rect.x, y, *CARTA_MAO),
                                 width=3, border_radius=9)

        # Aviso de decisão pendente (badge sobre a mesa)
        if devo_responder:
            quem = estado.get('valor_proposto', 3)
            rotulo = f'TRUCO! Valendo {quem} pontos — responda:'
            larg_t = FONTES['grande'].size(rotulo)[0] + 44
            badge = pygame.Rect(0, 0, larg_t, 46)
            badge.center = (LARG_JOGO // 2, 458)
            pygame.draw.rect(janela, (120, 60, 15), badge, border_radius=23)
            pygame.draw.rect(janela, LARANJA, badge, width=2, border_radius=23)
            texto(janela, rotulo, badge.centerx, badge.centery,
                  fonte='grande', cor=AMARELO, centro=True)

        # Timer (pílula com contagem)
        restante = cliente.timer_restante()
        if restante > 0 and cliente.timer_jogador:
            cor_pil = (140, 40, 40) if restante <= 10 else (20, 50, 35)
            rotulo = f'Vez de {cliente.timer_jogador}  •  {restante}s'
            larg_t = FONTES['normal'].size(rotulo)[0] + 32
            pil = pygame.Rect(20, ALTURA - 100, larg_t, 34)
            pygame.draw.rect(janela, cor_pil, pil, border_radius=17)
            pygame.draw.rect(janela, DOURADO if restante > 10 else VERMELHO,
                             pil, width=2, border_radius=17)
            texto(janela, rotulo, pil.centerx, pil.centery, centro=True)
        if cliente.status_msg:
            cor = VERMELHO if '[ERRO]' in cliente.status_msg else AMARELO
            texto(janela, cliente.status_msg, 20, ALTURA - 130, fonte='pequena', cor=cor)

        # Botões
        for botao, _ in botoes:
            botao.desenhar(janela)
        b_sair.desenhar(janela)

        # Chat (coluna direita)
        desenhar_chat(janela, cliente, campo_chat, LARG_JOGO + 10, 56,
                      LARGURA - LARG_JOGO - 20, ALTURA - 68)

        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Tela: conexão perdida                                              #
# ------------------------------------------------------------------ #

def tela_desconectado(janela, cliente):
    relogio = pygame.time.Clock()
    cx = LARGURA // 2 - 190
    b_reconectar = Botao('Reconectar', cx, 420, 180, 52)
    b_sair       = Botao('Sair', cx + 200, 420, 180, 52, cor=VERMELHO)

    while cliente.tela == 'desconectado':
        cliente.processar_fila()
        continuar, clique, _ = eventos_basicos()
        if not continuar:
            return False

        if clique:
            if b_sair.clicou(clique):
                return False
            if b_reconectar.clicou(clique):
                desenhar_fundo(janela)
                texto(janela, 'Reconectando...', LARGURA // 2, ALTURA // 2,
                      fonte='grande', cor=AMARELO, centro=True)
                pygame.display.flip()
                cliente.reconectar()
                break

        desenhar_fundo(janela)
        texto(janela, 'CONEXAO PERDIDA', LARGURA // 2, 220, fonte='titulo',
              cor=VERMELHO, centro=True)
        texto(janela, 'A conexao com o servidor foi encerrada.',
              LARGURA // 2, 290, centro=True)
        if cliente.sala_id:
            texto(janela, f'Havia uma partida em andamento na Sala {cliente.sala_id}.',
                  LARGURA // 2, 325, centro=True)
        b_reconectar.desenhar(janela)
        b_sair.desenhar(janela)
        desenhar_status(janela, cliente, y=510)
        pygame.display.flip()
        relogio.tick(FPS)
    return True


# ------------------------------------------------------------------ #
#  Loop principal                                                     #
# ------------------------------------------------------------------ #

def main():
    janela = inicializar()
    cliente = Cliente()
    try:
        cliente.conectar()
    except OSError:
        relogio = pygame.time.Clock()
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or ev.type == pygame.KEYDOWN or \
                   ev.type == pygame.MOUSEBUTTONDOWN:
                    pygame.quit()
                    return
            desenhar_fundo(janela)
            texto(janela, 'Nao foi possivel conectar ao broker em '
                  f'{BROKER_HOST}:{BROKER_PORT}', LARGURA // 2, 300, centro=True)
            texto(janela, 'Verifique se o servidor esta rodando.',
                  LARGURA // 2, 340, centro=True)
            texto(janela, 'Clique ou pressione qualquer tecla para sair.',
                  LARGURA // 2, 410, cor=CINZA_CLARO, centro=True)
            pygame.display.flip()
            relogio.tick(FPS)

    telas = {
        'inicio':       tela_inicio,
        'lobby':        tela_lobby,
        'aguardando':   tela_aguardando,
        'salas':        tela_salas,
        'espera_sala':  tela_espera_sala,
        'perfil':       tela_perfil,
        'ranking':      tela_ranking,
        'jogo':         tela_jogo,
        'desconectado': tela_desconectado,
    }

    rodando = True
    while rodando:
        cliente.processar_fila()
        tela = cliente.tela
        if tela in ('login', 'cadastro'):
            rodando = tela_formulario(janela, cliente, tela)
        elif tela in telas:
            rodando = telas[tela](janela, cliente)
        else:
            cliente.tela = 'inicio'

    cliente.fechar()
    pygame.quit()


if __name__ == '__main__':
    main()
