import hashlib
import psycopg2


def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()


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


def registrar_usuario(conn, nome, senha):
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
