# Truco Paulista Distribuído

Jogo de Truco Paulista multiplayer em modo terminal, desenvolvido para a disciplina de Sistemas Distribuídos — UTFPR Campus Campo Mourão.

## Arquitetura

```
[Cliente curses]  ──TCP:5000──►  [Broker]  ──TCP:5001──►  [Backend]
                                     │                         │
                                  [Redis]               [PostgreSQL]
```

- **Frontend** (`frontend/cliente.py`): interface terminal com `curses`, roda localmente.
- **Broker** (`broker/broker.py`): autentica o cliente, mantém a sessão e repassa mensagens ao backend.
- **Backend** (`backend/servidor.py`): lógica do jogo, gerencia salas e timers.
- **Redis**: estado das sessões e das partidas em andamento (com TTL).
- **PostgreSQL**: cadastro de usuários e histórico de partidas.

## Salas

| Salas | Tipo | Jogadores |
|-------|------|-----------|
| 1 – 13 | Normal | 4 (2 duplas) |
| 14 – 16 | 1v1 | 2 |

## Pré-requisitos

- Docker e Docker Compose
- Python 3.10+ (para rodar o cliente localmente)

> **Observação (Windows):** o módulo `curses` não está disponível no Python padrão do Windows.
> Para rodar o cliente em Windows, instale: `pip install windows-curses`

## Como rodar

```bash
# Subir os servidores (Redis, PostgreSQL, Broker, Backend)
make up

# Abrir o cliente
make cliente

# Ver informações do servidor
make info

# Rodar todos os testes
make test

# Ver logs dos containers
make logs

# Derrubar os servidores
make down

# Reiniciar e limpar banco de dados
make reset-db
```

## Protocolo

Todas as mensagens entre cliente, broker e backend são objetos JSON delimitados por `\n` via TCP.

Exemplos:

```json
{"tipo": "login", "nome": "joao", "senha": "1234"}
{"tipo": "ok", "mensagem": "Bem-vindo, joao!", "token": "..."}
{"tipo": "entrar_sala", "sala": 3}
{"tipo": "jogar_carta", "indice": 0}
{"tipo": "pedir_truco"}
{"tipo": "chat", "mensagem": "boa sorte!"}
```

## Testes

```bash
make test
# ou diretamente:
python3 -m pytest backend/tests/ broker/tests/ frontend/tests/ -v
```

232 testes cobrindo: lógica do jogo, Redis, PostgreSQL, servidor e broker.
