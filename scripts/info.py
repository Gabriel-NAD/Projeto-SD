#!/usr/bin/env python3
import os
import sys

try:
    import redis
    import psycopg2
except ImportError:
    print("Instale: pip3 install redis psycopg2-binary")
    sys.exit(1)

R_HOST = os.getenv('REDIS_HOST', 'localhost')
R_PORT = int(os.getenv('REDIS_PORT', 6379))
PG_DSN = (
    f"host={os.getenv('PG_HOST','localhost')} "
    f"dbname={os.getenv('PG_DB','truco')} "
    f"user={os.getenv('PG_USER','truco')} "
    f"password={os.getenv('PG_PASS','truco')}"
)


def main():
    # Redis
    try:
        r = redis.Redis(host=R_HOST, port=R_PORT, decode_responses=True)
        r.ping()
        sessoes_ativas  = len(r.keys('sessao:*'))
        salas_com_jogo  = len(r.keys('sala:*:estado'))
    except Exception as e:
        print(f"Erro ao conectar ao Redis ({R_HOST}:{R_PORT}): {e}")
        sys.exit(1)

    # PostgreSQL
    try:
        conn = psycopg2.connect(PG_DSN)
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM usuarios")
        total_usuarios = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM partidas WHERE encerrada_em IS NOT NULL")
        total_partidas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM partidas WHERE status = 'em_andamento'")
        partidas_ativas = cur.fetchone()[0]
        conn.close()
    except Exception as e:
        print(f"Erro ao conectar ao PostgreSQL: {e}")
        sys.exit(1)

    sep = '=' * 42
    print(sep)
    print('  INFORMACOES DO SERVIDOR  -  TRUCO')
    print(sep)
    print(f"  Usuarios cadastrados : {total_usuarios}")
    print(f"  Sessoes ativas       : {sessoes_ativas}")
    print(f"  Salas com jogo ativo : {salas_com_jogo}")
    print(f"  Partidas em andamento: {partidas_ativas}")
    print(f"  Partidas concluidas  : {total_partidas}")
    print(sep)


if __name__ == '__main__':
    main()
