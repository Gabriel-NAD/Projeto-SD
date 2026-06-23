import socket
import threading
import json
import uuid
import os
import redis
import psycopg2

import banco_postgres as bp
import banco_redis as br

# ------------------------------------------------------------------ #
#  Configurações                                                      #
# ------------------------------------------------------------------ #

HOST        = os.getenv('BROKER_HOST', '0.0.0.0')
PORT        = int(os.getenv('BROKER_PORT', 5000))
BACKEND_HOST = os.getenv('BACKEND_HOST', 'backend')
BACKEND_PORT = int(os.getenv('BACKEND_PORT', 5001))
R_HOST      = os.getenv('REDIS_HOST', 'redis')
R_PORT      = int(os.getenv('REDIS_PORT', 6379))
PG_DSN      = (
    f"host={os.getenv('PG_HOST','postgres')} "
    f"dbname={os.getenv('PG_DB','truco')} "
    f"user={os.getenv('PG_USER','truco')} "
    f"password={os.getenv('PG_PASS','truco')}"
)

_r      = None
_pg     = None
_pg_lock = threading.Lock()


# ------------------------------------------------------------------ #
#  Helpers de rede                                                    #
# ------------------------------------------------------------------ #

def _enviar(conn, msg):
    try:
        conn.sendall((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
    except OSError:
        pass


def _ler_mensagens(conn):
    """Gerador que lê mensagens JSON delimitadas por newline."""
    buffer = ''
    while True:
        try:
            data = conn.recv(4096).decode('utf-8')
        except OSError:
            break
        if not data:
            break
        buffer += data
        while '\n' in buffer:
            linha, buffer = buffer.split('\n', 1)
            linha = linha.strip()
            if not linha:
                continue
            try:
                yield json.loads(linha)
            except json.JSONDecodeError:
                continue


def _conectar_backend():
    """Abre e retorna uma conexão TCP com o backend."""
    conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    conn.connect((BACKEND_HOST, BACKEND_PORT))
    return conn


# ------------------------------------------------------------------ #
#  Autenticação                                                       #
# ------------------------------------------------------------------ #

def _handle_registro(msg, cliente_conn):
    nome  = msg.get('nome', '').strip()
    senha = msg.get('senha', '').strip()

    if not nome or not senha:
        _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Nome e senha obrigatórios'})
        return None

    if len(nome) > 50:
        _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Nome muito longo (máx 50 caracteres)'})
        return None

    with _pg_lock:
        ok = bp.registrar_usuario(_pg, nome, senha)

    if not ok:
        _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Nome de usuário já existe'})
        return None

    _enviar(cliente_conn, {'tipo': 'ok', 'mensagem': 'Cadastro realizado! Faça login.'})
    return None


def _handle_login(msg, cliente_conn):
    nome  = msg.get('nome', '').strip()
    senha = msg.get('senha', '').strip()

    if not nome or not senha:
        _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Nome e senha obrigatórios'})
        return None

    with _pg_lock:
        ok = bp.autenticar(_pg, nome, senha)

    if not ok:
        _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Usuário ou senha inválidos'})
        return None

    # Invalidar sessão anterior se existir
    token_antigo = br.token_por_nome(_r, nome)
    if token_antigo:
        br.remover_sessao(_r, token_antigo, nome)

    token = uuid.uuid4().hex
    br.salvar_sessao(_r, token, nome)

    _enviar(cliente_conn, {'tipo': 'ok', 'mensagem': f'Bem-vindo, {nome}!', 'token': token})
    return nome, token


# ------------------------------------------------------------------ #
#  Handler de cliente                                                 #
# ------------------------------------------------------------------ #

def handle_cliente(cliente_conn, addr):
    """
    Gerencia toda a sessão de um cliente:
    1. Aguarda registro ou login
    2. Após autenticado, abre conexão com o backend e roteia mensagens
    """
    nome  = None
    token = None
    backend_conn = None

    try:
        # Fase 1: autenticação (só aceita 'registro' ou 'login')
        for msg in _ler_mensagens(cliente_conn):
            tipo = msg.get('tipo')

            if tipo == 'registro':
                _handle_registro(msg, cliente_conn)
                continue

            if tipo == 'login':
                resultado = _handle_login(msg, cliente_conn)
                if resultado:
                    nome, token = resultado
                    break
                continue

            _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Faça login primeiro'})

        if not nome:
            return

        # Fase 2: conectar ao backend e iniciar relay bidirecional
        try:
            backend_conn = _conectar_backend()
        except OSError:
            _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Serviço indisponível. Tente novamente.'})
            return

        # Thread que lê do backend e encaminha ao cliente
        def backend_para_cliente():
            for msg in _ler_mensagens(backend_conn):
                _enviar(cliente_conn, msg)

        t = threading.Thread(target=backend_para_cliente, daemon=True)
        t.start()

        # Fase 3: ler do cliente, injetar 'usuario' e encaminhar ao backend
        for msg in _ler_mensagens(cliente_conn):
            tipo = msg.get('tipo')

            # Logout explícito
            if tipo == 'logout':
                break

            # Validar sessão a cada mensagem
            if not br.sessao_existe(_r, token):
                _enviar(cliente_conn, {'tipo': 'erro', 'mensagem': 'Sessão expirada. Faça login novamente.'})
                break

            msg['usuario'] = nome
            _enviar(backend_conn, msg)

    finally:
        if token:
            br.remover_sessao(_r, token, nome)
        if backend_conn:
            try:
                # Notificar backend da desconexão
                _enviar(backend_conn, {'tipo': 'desconexao', 'usuario': nome})
                backend_conn.close()
            except OSError:
                pass
        try:
            cliente_conn.close()
        except OSError:
            pass


# ------------------------------------------------------------------ #
#  Inicialização                                                      #
# ------------------------------------------------------------------ #

def iniciar_broker():
    global _r, _pg

    _r  = redis.Redis(host=R_HOST, port=R_PORT, decode_responses=True)
    _pg = psycopg2.connect(PG_DSN)
    bp.criar_tabelas(_pg)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen()
    print(f'Broker ouvindo em {HOST}:{PORT}')

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_cliente, args=(conn, addr), daemon=True)
        t.start()


if __name__ == '__main__':
    iniciar_broker()
