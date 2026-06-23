import hashlib
import psycopg2


def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


# ------------------------------------------------------------------ #
#  Tabelas                                                            #
# ------------------------------------------------------------------ #

def criar_tabelas(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                nome        VARCHAR(50) PRIMARY KEY,
                senha_hash  VARCHAR(64) NOT NULL,
                vitorias    INTEGER DEFAULT 0,
                partidas    INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS partidas (
                id           SERIAL PRIMARY KEY,
                sala         INTEGER NOT NULL,
                tipo         VARCHAR(10) NOT NULL,
                vencedores   VARCHAR(200),
                perdedores   VARCHAR(200),
                status       VARCHAR(20) NOT NULL DEFAULT 'em_andamento',
                iniciada_em  TIMESTAMP DEFAULT NOW(),
                encerrada_em TIMESTAMP
            )
        """)
    conn.commit()


# ------------------------------------------------------------------ #
#  Usuários                                                           #
# ------------------------------------------------------------------ #

def registrar_usuario(conn, nome, senha):
    """Retorna True se cadastrado com sucesso, False se nome já existe."""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO usuarios (nome, senha_hash) VALUES (%s, %s)",
                (nome, hash_senha(senha))
            )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        conn.rollback()
        return False


def autenticar(conn, nome, senha):
    """Retorna True se nome e senha são válidos."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM usuarios WHERE nome = %s AND senha_hash = %s",
            (nome, hash_senha(senha))
        )
        return cur.fetchone() is not None


def usuario_existe(conn, nome):
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM usuarios WHERE nome = %s", (nome,))
        return cur.fetchone() is not None


def obter_perfil(conn, nome):
    """Retorna dict {nome, vitorias, partidas, derrotas} ou None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT nome, vitorias, partidas FROM usuarios WHERE nome = %s",
            (nome,)
        )
        row = cur.fetchone()
    if row is None:
        return None
    nome_, vitorias, partidas = row
    return {
        'nome': nome_,
        'vitorias': vitorias,
        'partidas': partidas,
        'derrotas': partidas - vitorias,
    }


def obter_ranking(conn, limite=10):
    """Retorna lista de {nome, vitorias} ordenada por vitórias decrescente."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT nome, vitorias FROM usuarios ORDER BY vitorias DESC LIMIT %s",
            (limite,)
        )
        rows = cur.fetchall()
    return [{'nome': r[0], 'vitorias': r[1]} for r in rows]


def registrar_vitoria(conn, nome):
    """Incrementa vitórias e partidas do jogador."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET vitorias = vitorias + 1, partidas = partidas + 1 WHERE nome = %s",
            (nome,)
        )
    conn.commit()


def registrar_derrota(conn, nome):
    """Incrementa apenas partidas (derrotas = partidas - vitorias)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE usuarios SET partidas = partidas + 1 WHERE nome = %s",
            (nome,)
        )
    conn.commit()


def total_usuarios(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM usuarios")
        return cur.fetchone()[0]


# ------------------------------------------------------------------ #
#  Partidas                                                           #
# ------------------------------------------------------------------ #

def iniciar_partida(conn, sala_id, tipo):
    """Registra início de partida e retorna o ID gerado."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO partidas (sala, tipo) VALUES (%s, %s) RETURNING id",
            (sala_id, tipo)
        )
        partida_id = cur.fetchone()[0]
    conn.commit()
    return partida_id


def encerrar_partida(conn, partida_id, vencedores, perdedores, status):
    """
    Finaliza a partida.
    vencedores/perdedores: listas de nomes.
    status: 'completa' ou 'wo'.
    """
    venc_str = ','.join(vencedores) if vencedores else ''
    perd_str = ','.join(perdedores) if perdedores else ''
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE partidas
               SET vencedores = %s, perdedores = %s,
                   status = %s, encerrada_em = NOW()
               WHERE id = %s""",
            (venc_str, perd_str, status, partida_id)
        )
    conn.commit()


def total_partidas(conn):
    """Retorna total de partidas encerradas."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM partidas WHERE encerrada_em IS NOT NULL"
        )
        return cur.fetchone()[0]
