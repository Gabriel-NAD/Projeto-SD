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
        self.senha      = None
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

        self._fila    = queue.Queue()
        self._ativo   = True
        self.conectado = True

    def conectar(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((BROKER_HOST, BROKER_PORT))
        self.conectado = True
        threading.Thread(target=self._receber, daemon=True).start()

    def _reabrir_conexao(self):
        """Fecha a conexão antiga (se houver) e abre uma nova com o broker."""
        if self.conn:
            try:
                self.conn.close()
            except OSError:
                pass
        self.status_msg  = ''
        self.estado_jogo = None
        self.conectar()

    def reconectar(self):
        """Rota padrão de reconexão: reabre a conexão com o broker e,
        com as credenciais salvas, reloga e volta para onde estava
        (partida em andamento, sala de espera ou lobby)."""
        try:
            self._reabrir_conexao()
        except OSError:
            self.conectado = False
            self.status_msg = '[ERRO] Nao foi possivel reconectar ao broker'
            self.tela = 'desconectado'
            return

        if not (self.nome and self.senha):
            # Sem credenciais salvas: volta para o início
            self.tela = 'inicio'
            return

        self.enviar({'tipo': 'login', 'nome': self.nome, 'senha': self.senha})
        if not self._aguardar_tela('lobby'):
            self.tela = 'desconectado'
            if '[ERRO]' not in self.status_msg:
                self.status_msg = '[ERRO] Falha ao relogar no servidor'
            return

        if not self.sala_id:
            return  # não estava em sala: fica no lobby

        # Tenta voltar para a sala em que estava
        sala_num = self.sala_id
        self.status_msg = ''
        self.enviar({'tipo': 'entrar_sala', 'sala': sala_num})
        deadline = time.time() + 5
        while time.time() < deadline:
            self.processar_fila()
            if self.tela == 'jogo':
                return  # reconectou na partida
            if '[ERRO]' in self.status_msg:
                # Não deu para voltar (ex: reconexão já usada, partida
                # encerrada por W.O.): segue para o lobby com o motivo
                self.sala_id = None
                self.tela = 'lobby'
                return
            if 'Entrou' in self.status_msg:
                # Partida acabou enquanto desconectado e a sala foi
                # reiniciada: entrou como jogador novo, aguarda início
                self.chat_msgs = []   # partida nova, chat limpo
                self.tela = 'espera_sala'
                return
            time.sleep(0.1)

        self.sala_id = None
        self.tela = 'lobby'

    def _aguardar_tela(self, alvo, timeout=5):
        """Processa a fila até a tela mudar para `alvo` ou dar erro/timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.processar_fila()
            if self.tela == alvo:
                return True
            if '[ERRO]' in self.status_msg:
                return False
            time.sleep(0.1)
        return False

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

        self.conectado = False
        # Rota padrão de desconexão: uma única tela decide entre
        # reconectar ou sair, independente de onde a queda ocorreu.
        if self.tela not in ('inicio', 'login', 'cadastro'):
            self.tela = 'desconectado'

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
            self.chat_msgs   = []   # chat existe apenas durante a partida
            self.status_msg  = f"Partida encerrada: {resultado} ({motivo})"
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


