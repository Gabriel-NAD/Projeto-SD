import curses
import socket
import threading
import json
import queue
import time
import os

BROKER_HOST = os.getenv('BROKER_HOST', 'localhost')
BROKER_PORT = int(os.getenv('BROKER_PORT', 5000))
MAX_CHAT    = 20

# ------------------------------------------------------------------ #
#  Estado do cliente                                                  #
# ------------------------------------------------------------------ #

class Cliente:
    def __init__(self):
        self.conn       = None
        self.nome       = None
        self.sala_id    = None
        self.tela       = 'inicio'

        self.estado_jogo   = None
        self.lista_salas   = []
        self.perfil        = None
        self.ranking_lista = []
        self.chat_msgs     = []
        self.status_msg    = ''

        self.timer_total   = 0
        self.timer_inicio  = 0.0
        self.timer_jogador = ''

        self._fila  = queue.Queue()
        self._ativo = True

    def conectar(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((BROKER_HOST, BROKER_PORT))
        threading.Thread(target=self._receber, daemon=True).start()

    def enviar(self, msg):
        if self.conn:
            try:
                self.conn.sendall(
                    (json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8')
                )
            except OSError:
                pass

    def _receber(self):
        buffer = ''
        while self._ativo:
            try:
                data = self.conn.recv(4096).decode('utf-8')
            except OSError:
                break
            if not data:
                break
            buffer += data
            while '\n' in buffer:
                linha, buffer = buffer.split('\n', 1)
                linha = linha.strip()
                if linha:
                    try:
                        self._fila.put(json.loads(linha))
                    except json.JSONDecodeError:
                        pass

    def processar_fila(self):
        mudou = False
        while not self._fila.empty():
            try:
                msg = self._fila.get_nowait()
            except queue.Empty:
                break
            self._processar_msg(msg)
            mudou = True
        return mudou

    def _processar_msg(self, msg):
        tipo = msg.get('tipo')

        if tipo == 'ok':
            self.status_msg = msg.get('mensagem', '')
            if 'token' in msg:
                self.tela = 'lobby'

        elif tipo == 'erro':
            self.status_msg = f"[ERRO] {msg.get('mensagem', '')}"

        elif tipo == 'salas':
            self.lista_salas = msg.get('lista', [])
            self.tela = 'salas'

        elif tipo == 'perfil':
            self.perfil = dict(msg)
            self.tela = 'perfil'

        elif tipo == 'ranking':
            self.ranking_lista = msg.get('lista', [])
            self.tela = 'ranking'

        elif tipo == 'estado_jogo':
            self.estado_jogo = msg.get('dados', {})
            self.tela = 'jogo'

        elif tipo == 'chat':
            self._add_chat(f"{msg.get('de','?')}: {msg.get('mensagem','')}")

        elif tipo == 'aviso':
            self._add_chat(f">>> {msg.get('mensagem','')}")

        elif tipo == 'desconexao':
            jogador = msg.get('jogador', '?')
            tempo   = msg.get('tempo_restante', 60)
            self._add_chat(f">>> {jogador} desconectou ({tempo}s para reconectar)")

        elif tipo == 'decisao_pendente':
            acao  = msg.get('acao', '?')
            timer = msg.get('timer', 30)
            self._add_chat(f">>> Decisao pendente: {acao} ({timer}s)")

        elif tipo == 'timer_turno':
            self.timer_total   = msg.get('segundos', 0)
            self.timer_inicio  = time.time()
            self.timer_jogador = msg.get('jogador', '')

        elif tipo == 'fim_partida':
            resultado = msg.get('resultado', '').upper()
            motivo    = msg.get('motivo', '')
            self._add_chat(f">>> Partida encerrada: {resultado} ({motivo})")
            self.status_msg  = f"Partida encerrada: {resultado}"
            self.estado_jogo = None
            self.sala_id     = None
            self.tela        = 'lobby'

    def _add_chat(self, texto):
        self.chat_msgs.append(texto)
        if len(self.chat_msgs) > MAX_CHAT:
            self.chat_msgs.pop(0)

    def timer_restante(self):
        if not self.timer_total:
            return 0
        return max(0, self.timer_total - int(time.time() - self.timer_inicio))

    def fechar(self):
        self._ativo = False
        if self.conn:
            try:
                self.conn.close()
            except OSError:
                pass


# ------------------------------------------------------------------ #
#  Helpers curses                                                     #
# ------------------------------------------------------------------ #

def _put(win, y, x, texto, attr=0):
    try:
        max_y, max_x = win.getmaxyx()
        if y < 0 or y >= max_y or x < 0 or x >= max_x:
            return
        texto = str(texto)[:max(0, max_x - x - 1)]
        if not texto:
            return
        if attr:
            win.addstr(y, x, texto, attr)
        else:
            win.addstr(y, x, texto)
    except curses.error:
        pass


def _linha(win, y, char='─'):
    max_y, max_x = win.getmaxyx()
    if 0 <= y < max_y:
        _put(win, y, 0, char * (max_x - 1))


def _centralizar(win, y, texto, attr=0):
    _, max_x = win.getmaxyx()
    x = max(0, (max_x - len(texto)) // 2)
    _put(win, y, x, texto, attr)


def ler_texto(stdscr, y, x, max_len=50, ocultar=False, prompt=''):
    if prompt:
        _put(stdscr, y, x, prompt)
        x += len(prompt)
    curses.curs_set(1)
    texto = ''
    while True:
        exibido = ('*' * len(texto) if ocultar else texto).ljust(max_len)[:max_len]
        _put(stdscr, y, x, exibido, curses.A_UNDERLINE)
        try:
            stdscr.move(y, x + len(texto))
        except curses.error:
            pass
        stdscr.refresh()
        ch = stdscr.getch()
        if ch in (10, 13):
            break
        elif ch == 27:
            texto = ''
            break
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            texto = texto[:-1]
        elif 32 <= ch <= 126 and len(texto) < max_len:
            texto += chr(ch)
    curses.curs_set(0)
    return texto.strip()


# ------------------------------------------------------------------ #
#  Tela: início                                                       #
# ------------------------------------------------------------------ #

def tela_inicio(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 2, ' TRUCO PAULISTA ', curses.A_BOLD | curses.A_REVERSE)
    _centralizar(stdscr, 4, 'Jogo de cartas distribuido')
    _put(stdscr, 7, 4, '[1] Login')
    _put(stdscr, 8, 4, '[2] Cadastro')
    _put(stdscr, 9, 4, '[3] Sair')
    _put(stdscr, 11, 4, cliente.status_msg)
    stdscr.refresh()

    stdscr.timeout(-1)
    ch = stdscr.getch()
    stdscr.timeout(100)

    if ch == ord('1'):
        cliente.tela = 'login'
    elif ch == ord('2'):
        cliente.tela = 'cadastro'
    elif ch == ord('3'):
        return False
    return True


# ------------------------------------------------------------------ #
#  Tela: login                                                        #
# ------------------------------------------------------------------ #

def tela_login(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 1, ' LOGIN ', curses.A_BOLD)
    _put(stdscr, 4, 4, 'Nome de usuario:')
    nome = ler_texto(stdscr, 5, 4, max_len=50)
    if not nome:
        cliente.tela = 'inicio'
        return True

    _put(stdscr, 7, 4, 'Senha:')
    senha = ler_texto(stdscr, 8, 4, max_len=50, ocultar=True)
    if not senha:
        cliente.tela = 'inicio'
        return True

    cliente.nome = nome
    cliente.enviar({'tipo': 'login', 'nome': nome, 'senha': senha})

    _put(stdscr, 10, 4, 'Aguardando...')
    stdscr.refresh()
    deadline = time.time() + 5
    while time.time() < deadline:
        cliente.processar_fila()
        if cliente.tela == 'lobby':
            return True
        if '[ERRO]' in cliente.status_msg:
            _put(stdscr, 10, 4, cliente.status_msg + '                ')
            stdscr.refresh()
            stdscr.timeout(-1)
            stdscr.getch()
            stdscr.timeout(100)
            cliente.status_msg = ''
            cliente.tela = 'inicio'
            return True
        time.sleep(0.1)

    cliente.status_msg = '[ERRO] Servidor nao respondeu'
    cliente.tela = 'inicio'
    return True


# ------------------------------------------------------------------ #
#  Tela: cadastro                                                     #
# ------------------------------------------------------------------ #

def tela_cadastro(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 1, ' CADASTRO ', curses.A_BOLD)
    _put(stdscr, 4, 4, 'Escolha um nome de usuario:')
    nome = ler_texto(stdscr, 5, 4, max_len=50)
    if not nome:
        cliente.tela = 'inicio'
        return True

    _put(stdscr, 7, 4, 'Escolha uma senha:')
    senha = ler_texto(stdscr, 8, 4, max_len=50, ocultar=True)
    if not senha:
        cliente.tela = 'inicio'
        return True

    cliente.enviar({'tipo': 'registro', 'nome': nome, 'senha': senha})

    _put(stdscr, 10, 4, 'Aguardando...')
    stdscr.refresh()
    deadline = time.time() + 5
    while time.time() < deadline:
        cliente.processar_fila()
        if 'realizado' in cliente.status_msg.lower():
            _put(stdscr, 10, 4, cliente.status_msg + ' Pressione ENTER.')
            stdscr.refresh()
            stdscr.timeout(-1)
            stdscr.getch()
            stdscr.timeout(100)
            cliente.status_msg = ''
            cliente.tela = 'inicio'
            return True
        if '[ERRO]' in cliente.status_msg:
            _put(stdscr, 10, 4, cliente.status_msg)
            stdscr.refresh()
            stdscr.timeout(-1)
            stdscr.getch()
            stdscr.timeout(100)
            cliente.status_msg = ''
            cliente.tela = 'inicio'
            return True
        time.sleep(0.1)

    cliente.tela = 'inicio'
    return True


# ------------------------------------------------------------------ #
#  Tela: lobby                                                        #
# ------------------------------------------------------------------ #

def tela_lobby(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 1, f' Bem-vindo, {cliente.nome}! ', curses.A_BOLD)
    _linha(stdscr, 2)
    _put(stdscr, 4, 4, '[1] Ver Salas')
    _put(stdscr, 5, 4, '[2] Meu Perfil')
    _put(stdscr, 6, 4, '[3] Ranking Global')
    _put(stdscr, 7, 4, '[4] Sair')
    _put(stdscr, 9, 4, cliente.status_msg)
    stdscr.refresh()

    stdscr.timeout(-1)
    ch = stdscr.getch()
    stdscr.timeout(100)

    if ch == ord('1'):
        cliente.enviar({'tipo': 'listar_salas'})
        cliente.tela = 'aguardando'
    elif ch == ord('2'):
        cliente.enviar({'tipo': 'meu_perfil'})
        cliente.tela = 'aguardando'
    elif ch == ord('3'):
        cliente.enviar({'tipo': 'ranking'})
        cliente.tela = 'aguardando'
    elif ch == ord('4'):
        return False
    return True


def tela_aguardando(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 5, 'Aguardando servidor...')
    stdscr.refresh()
    deadline = time.time() + 5
    while time.time() < deadline:
        cliente.processar_fila()
        if cliente.tela != 'aguardando':
            return True
        time.sleep(0.1)
    cliente.tela = 'lobby'
    return True


# ------------------------------------------------------------------ #
#  Tela: lista de salas                                               #
# ------------------------------------------------------------------ #

def tela_salas(stdscr, cliente):
    while True:
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()
        _centralizar(stdscr, 0, ' SALAS DISPONIVEIS ', curses.A_BOLD | curses.A_REVERSE)
        _linha(stdscr, 1)

        cabecalho = f"{'SALA':<16} {'JOGADORES':<12} {'STATUS'}"
        _put(stdscr, 2, 2, cabecalho, curses.A_BOLD)
        _linha(stdscr, 3, '─')

        salas = cliente.lista_salas
        for i, sala in enumerate(salas):
            if 4 + i >= max_y - 4:
                break
            sid    = sala.get('id', '?')
            tipo   = sala.get('tipo', 'normal')
            jogs   = sala.get('jogadores', 0)
            maxi   = sala.get('max', 4)
            status = sala.get('status', 'aguardando')
            nome_sala = f"Sala {sid}" + (' (1v1)' if tipo == '1v1' else '      ')
            linha = f"{nome_sala:<16} {jogs}/{maxi:<10} {status}"
            attr = curses.A_DIM if status == 'jogando' else 0
            _put(stdscr, 4 + i, 2, linha, attr)

        _linha(stdscr, max_y - 4)
        _put(stdscr, max_y - 3, 2,
             'Digite o numero da sala e ENTER | [A] Atualizar | [B] Voltar')
        _put(stdscr, max_y - 2, 2, cliente.status_msg)
        stdscr.refresh()

        stdscr.timeout(-1)
        ch = stdscr.getch()
        stdscr.timeout(100)

        if ch in (ord('b'), ord('B')):
            cliente.tela = 'lobby'
            return True

        if ch in (ord('a'), ord('A')):
            cliente.enviar({'tipo': 'listar_salas'})
            deadline = time.time() + 3
            while time.time() < deadline:
                cliente.processar_fila()
                if cliente.tela == 'salas':
                    break
                time.sleep(0.1)
            continue

        if ord('0') <= ch <= ord('9'):
            digitos = chr(ch)
            stdscr.timeout(800)
            while True:
                c2 = stdscr.getch()
                if c2 == -1 or not (ord('0') <= c2 <= ord('9')):
                    break
                digitos += chr(c2)
            stdscr.timeout(100)

            try:
                sala_num = int(digitos)
            except ValueError:
                continue

            if 1 <= sala_num <= 16:
                cliente.status_msg = ''
                cliente.enviar({'tipo': 'entrar_sala', 'sala': sala_num})
                cliente.sala_id = sala_num

                deadline = time.time() + 5
                while time.time() < deadline:
                    cliente.processar_fila()
                    if cliente.tela == 'jogo':
                        return True
                    if '[ERRO]' in cliente.status_msg:
                        break
                    # Recebeu ok (entrou na sala) mas jogo ainda não começou
                    if cliente.status_msg and '[ERRO]' not in cliente.status_msg:
                        cliente.tela = 'espera_sala'
                        return True
                    time.sleep(0.1)
            else:
                cliente.status_msg = '[ERRO] Sala invalida (1-16)'


# ------------------------------------------------------------------ #
#  Tela: espera na sala                                               #
# ------------------------------------------------------------------ #

def tela_espera_sala(stdscr, cliente):
    while cliente.tela == 'espera_sala':
        cliente.processar_fila()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        _centralizar(stdscr, 1, f' Sala {cliente.sala_id} ', curses.A_BOLD | curses.A_REVERSE)
        _linha(stdscr, 2)
        _centralizar(stdscr, 4, 'Aguardando jogadores entrarem...')

        msgs = cliente.chat_msgs[-(max_y - 10):]
        for i, msg in enumerate(msgs):
            _put(stdscr, 6 + i, 2, msg[:max_x - 4])

        _linha(stdscr, max_y - 3)
        _put(stdscr, max_y - 2, 2, '[S] Sair da sala')
        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (ord('s'), ord('S')):
            cliente.enviar({'tipo': 'sair_sala'})
            cliente.sala_id = None
            cliente.tela = 'lobby'
            return True

    # tela mudou para 'jogo' (game started)
    return True


# ------------------------------------------------------------------ #
#  Tela: perfil                                                       #
# ------------------------------------------------------------------ #

def tela_perfil(stdscr, cliente):
    stdscr.clear()
    _centralizar(stdscr, 1, ' MEU PERFIL ', curses.A_BOLD)
    _linha(stdscr, 2)
    p = cliente.perfil or {}
    _put(stdscr, 4,  4, f"Nome:     {p.get('nome', '-')}")
    _put(stdscr, 5,  4, f"Partidas: {p.get('partidas', 0)}")
    _put(stdscr, 6,  4, f"Vitorias: {p.get('vitorias', 0)}")
    _put(stdscr, 7,  4, f"Derrotas: {p.get('derrotas', 0)}")
    _linha(stdscr, 9)
    _put(stdscr, 10, 4, '[ENTER] Voltar ao lobby')
    stdscr.refresh()

    stdscr.timeout(-1)
    stdscr.getch()
    stdscr.timeout(100)
    cliente.tela = 'lobby'
    return True


# ------------------------------------------------------------------ #
#  Tela: ranking                                                      #
# ------------------------------------------------------------------ #

def tela_ranking(stdscr, cliente):
    stdscr.clear()
    max_y, _ = stdscr.getmaxyx()
    _centralizar(stdscr, 0, ' RANKING GLOBAL ', curses.A_BOLD | curses.A_REVERSE)
    _linha(stdscr, 1)
    _put(stdscr, 2, 2, f"{'#':<4} {'NOME':<30} {'VITORIAS'}", curses.A_BOLD)
    _linha(stdscr, 3, '─')

    for i, entry in enumerate(cliente.ranking_lista):
        if 4 + i >= max_y - 3:
            break
        nome = entry.get('nome', '?')
        vit  = entry.get('vitorias', 0)
        attr = curses.A_BOLD if i == 0 else 0
        _put(stdscr, 4 + i, 2, f"{i+1:<4} {nome:<30} {vit}", attr)

    _linha(stdscr, max_y - 3)
    _put(stdscr, max_y - 2, 2, '[ENTER] Voltar')
    stdscr.refresh()

    stdscr.timeout(-1)
    stdscr.getch()
    stdscr.timeout(100)
    cliente.tela = 'lobby'
    return True


# ------------------------------------------------------------------ #
#  Tela: jogo                                                         #
# ------------------------------------------------------------------ #

def _info_jogador(jogadores, nome):
    return next((j for j in jogadores if j['nome'] == nome), {})


def tela_jogo(stdscr, cliente):
    modo_chat     = False
    selecao_carta = None  # None | 'normal' | 'coberta'

    while cliente.tela == 'jogo':
        cliente.processar_fila()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        if max_y < 20 or max_x < 60:
            _centralizar(stdscr, max_y // 2, 'Terminal muito pequeno! (min 60x20)')
            stdscr.refresh()
            time.sleep(0.5)
            continue

        estado   = cliente.estado_jogo or {}
        col_div  = max_x * 3 // 5
        jogadores = estado.get('jogadores', [])
        eu        = _info_jogador(jogadores, cliente.nome)
        minha_dupla    = eu.get('dupla')
        dupla_pediu    = estado.get('dupla_pediu_truco')
        status_jogo    = estado.get('status', 'jogando')
        mao_de_11      = estado.get('mao_de_11', False)
        minha_vez      = eu.get('vez', False)
        truco_pendente = (status_jogo == 'truco_pendente')
        devo_responder = truco_pendente and (minha_dupla is not None) and (minha_dupla != dupla_pediu)

        # Verifica se minha dupla é a que tem 11 pontos
        placar = estado.get('placar', [0, 0])
        dupla_com_11 = next((i for i, p in enumerate(placar) if p == 11), None)
        posso_correr_11 = mao_de_11 and (minha_dupla == dupla_com_11)

        adversarios      = [j for j in jogadores if j.get('dupla') != minha_dupla]
        minha_dupla_list = [j for j in jogadores if j.get('dupla') == minha_dupla]

        # ---- CABEÇALHO ----
        sala_str = f"Sala {estado.get('sala','?')} ({estado.get('tipo','?')})"
        rodada   = estado.get('rodada_atual', 1)
        mao_val  = estado.get('mao_valor', 1)
        vira     = estado.get('vira', '?')
        vp       = estado.get('valor_proposto')
        vp_str   = f"  Truco: {vp}pts" if vp else ''
        header   = f" {sala_str}  R{rodada}/3  Mao: {mao_val}pts  Vira: {vira}{vp_str} "
        _centralizar(stdscr, 0, header, curses.A_BOLD | curses.A_REVERSE)
        _linha(stdscr, 1)

        # ---- PAINEL ESQUERDO ----
        linha = 2
        _put(stdscr, linha, 1, 'ADVERSARIOS', curses.A_BOLD)
        linha += 1
        for j in adversarios:
            online = '[ON] ' if j.get('online') else '[OFF]'
            vez    = '► ' if j.get('vez') else '  '
            _put(stdscr, linha, 2, f"{vez}{online} {j['nome']}  [{j['n_cartas']} cartas]")
            linha += 1

        _linha(stdscr, linha, '·')
        linha += 1

        _put(stdscr, linha, 1, 'MESA', curses.A_BOLD)
        linha += 1
        mesa = estado.get('mesa', [])
        if mesa:
            for jogada in mesa:
                carta = jogada.get('carta', '????')
                jog   = jogada.get('jogador', '?')
                cob   = ' [coberta]' if jogada.get('coberta') else ''
                _put(stdscr, linha, 2, f"{jog:<14} {carta}{cob}")
                linha += 1
        else:
            _put(stdscr, linha, 2, '(nenhuma carta ainda)')
            linha += 1

        _linha(stdscr, linha, '·')
        linha += 1

        _put(stdscr, linha, 1, 'SUA DUPLA', curses.A_BOLD)
        linha += 1
        for j in minha_dupla_list:
            online = '[ON] ' if j.get('online') else '[OFF]'
            vez    = '► ' if j.get('vez') else '  '
            if j['nome'] == cliente.nome:
                suas_cartas = estado.get('suas_cartas', [])
                cartas_str  = '  '.join(f'[{c}]' for c in suas_cartas)
                _put(stdscr, linha, 2, f"{vez}{online} Voce: {cartas_str}")
            else:
                _put(stdscr, linha, 2, f"{vez}{online} {j['nome']}: [{j['n_cartas']} cartas]")
            linha += 1

        _put(stdscr, linha, 1, f"PLACAR: A={placar[0]}  B={placar[1]}", curses.A_BOLD)

        # ---- PAINEL DIREITO: CHAT ----
        _put(stdscr, 2, col_div + 1, 'CHAT', curses.A_BOLD)
        chat_linhas_max = max(1, max_y - 8)
        for i, msg in enumerate(cliente.chat_msgs[-chat_linhas_max:]):
            _put(stdscr, 3 + i, col_div + 1, msg[:max_x - col_div - 2])

        for r in range(2, max_y - 5):
            _put(stdscr, r, col_div, '│')

        # ---- BARRA DE AÇÕES ----
        _linha(stdscr, max_y - 6)

        if selecao_carta:
            suas_cartas = estado.get('suas_cartas', [])
            opcoes = '  '.join(f'[{i+1}] {c}' for i, c in enumerate(suas_cartas))
            _put(stdscr, max_y - 5, 1, f'Carta: {opcoes}  [ESC] Cancelar')

        elif modo_chat:
            _put(stdscr, max_y - 5, 1, 'Mensagem: ', curses.A_BOLD)

        elif devo_responder:
            _put(stdscr, max_y - 5, 1,
                 '[A] Aceitar truco  [R] Retruco  [C] Correr')

        elif mao_de_11 and posso_correr_11:
            _put(stdscr, max_y - 5, 1,
                 '[1-3] Jogar carta  [C] Correr (dar 1 ponto ao adversario)')

        elif minha_vez and not truco_pendente:
            _put(stdscr, max_y - 5, 1,
                 '[1] Jogar  [2] Coberta  [3] Truco  [4] Correr  [T] Chat  [S] Sair')

        else:
            _put(stdscr, max_y - 5, 1, 'Aguardando...  [T] Chat  [S] Sair sala')

        # Timer
        restante  = cliente.timer_restante()
        timer_jog = cliente.timer_jogador
        if restante > 0:
            cor = curses.A_BOLD if restante <= 10 else 0
            _put(stdscr, max_y - 4, 1, f'Vez de {timer_jog} — {restante}s', cor)
        if cliente.status_msg:
            _put(stdscr, max_y - 3, 1, cliente.status_msg)

        stdscr.refresh()

        # ---- INPUT ----
        if modo_chat:
            stdscr.timeout(-1)
            texto = ler_texto(stdscr, max_y - 5, 11, max_len=max_x - 14)
            stdscr.timeout(100)
            if texto:
                cliente.enviar({'tipo': 'chat', 'mensagem': texto})
            modo_chat = False
            continue

        ch = stdscr.getch()
        if ch == -1:
            continue

        # Ações globais (sempre disponíveis)
        if ch in (ord('s'), ord('S')):
            cliente.enviar({'tipo': 'sair_sala'})
            cliente.sala_id     = None
            cliente.estado_jogo = None
            cliente.tela        = 'lobby'
            return True

        if ch in (ord('t'), ord('T')):
            modo_chat = True
            continue

        if ch == 27 and selecao_carta:
            selecao_carta = None
            continue

        # Seleção de carta (após pressionar [1] ou [2])
        if selecao_carta:
            suas_cartas = estado.get('suas_cartas', [])
            if ord('1') <= ch <= ord('0') + len(suas_cartas):
                idx     = ch - ord('1')
                coberta = (selecao_carta == 'coberta')
                cliente.enviar({
                    'tipo': 'jogar_coberta' if coberta else 'jogar_carta',
                    'indice': idx,
                })
                cliente.status_msg = ''
                selecao_carta = None
            continue

        # Resposta a truco (quando adversário pediu)
        if devo_responder:
            if ch in (ord('a'), ord('A')):
                cliente.enviar({'tipo': 'responder_truco', 'resposta': 'aceitar'})
            elif ch in (ord('r'), ord('R')):
                cliente.enviar({'tipo': 'responder_truco', 'resposta': 'aumentar'})
            elif ch in (ord('c'), ord('C')):
                cliente.enviar({'tipo': 'votar_correr', 'voto': True})
            continue

        # Correr na mão de 11
        if mao_de_11 and posso_correr_11 and ch in (ord('c'), ord('C')):
            cliente.enviar({'tipo': 'correr_mao_de_11'})
            continue

        # Ações normais (minha vez, sem truco pendente)
        if minha_vez and not truco_pendente:
            if ch == ord('1'):
                selecao_carta = 'normal'
            elif ch == ord('2'):
                selecao_carta = 'coberta'
            elif ch == ord('3'):
                cliente.enviar({'tipo': 'pedir_truco'})
            elif ch == ord('4'):
                cliente.enviar({'tipo': 'votar_correr', 'voto': True})

    return True


# ------------------------------------------------------------------ #
#  Loop principal                                                     #
# ------------------------------------------------------------------ #

def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    stdscr.timeout(100)

    cliente = Cliente()
    try:
        cliente.conectar()
    except OSError:
        stdscr.clear()
        _centralizar(stdscr, 5,
                     f'Nao foi possivel conectar ao broker em {BROKER_HOST}:{BROKER_PORT}')
        _centralizar(stdscr, 6, 'Verifique se o servidor esta rodando.')
        _centralizar(stdscr, 8, 'Pressione qualquer tecla para sair.')
        stdscr.timeout(-1)
        stdscr.getch()
        return

    rodando = True
    while rodando:
        cliente.processar_fila()
        tela = cliente.tela

        if tela == 'inicio':
            rodando = tela_inicio(stdscr, cliente)
        elif tela == 'login':
            tela_login(stdscr, cliente)
        elif tela == 'cadastro':
            tela_cadastro(stdscr, cliente)
        elif tela == 'lobby':
            rodando = tela_lobby(stdscr, cliente)
        elif tela == 'aguardando':
            tela_aguardando(stdscr, cliente)
        elif tela == 'salas':
            tela_salas(stdscr, cliente)
        elif tela == 'espera_sala':
            tela_espera_sala(stdscr, cliente)
        elif tela == 'perfil':
            tela_perfil(stdscr, cliente)
        elif tela == 'ranking':
            tela_ranking(stdscr, cliente)
        elif tela == 'jogo':
            tela_jogo(stdscr, cliente)

    cliente.fechar()


if __name__ == '__main__':
    curses.wrapper(main)
