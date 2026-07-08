# Truco Paulista Distribuído

Jogo de Truco Paulista multiplayer com interface gráfica em `pygame`,
desenvolvido para a disciplina de Sistemas Distribuídos — UTFPR Campus
Campo Mourão.

Documentação completa (arquitetura, protocolo, código e roteiro de
demonstração): **[DOCUMENTACAO.md](DOCUMENTACAO.md)**.

## Arquitetura

```
[Cliente pygame]  ──TCP:5000──►  [Broker]  ──TCP:5001──►  [Backend]
                                     │                         │
                                  [Redis]               [PostgreSQL]
```

- **Frontend** (`frontend/interface.py` + `frontend/cliente.py`): interface
  gráfica com `pygame`, roda na máquina do jogador. A comunicação com o
  servidor fica na classe `Cliente` (`cliente.py`) e as telas em
  `interface.py`.
- **Broker** (`broker/broker.py`): autentica o cliente, mantém a sessão e
  repassa mensagens ao backend. É o único ponto de entrada do sistema.
- **Backend** (`backend/servidor.py`): lógica do jogo, salas, timers e
  reconexão.
- **Redis**: estado das sessões e das partidas em andamento (com TTL).
- **PostgreSQL**: cadastro de usuários e histórico de partidas.

## Salas

| Salas | Tipo | Jogadores |
|-------|------|-----------|
| 1 – 13 | Normal | 4 (2 duplas) |
| 14 – 16 | 1v1 | 2 |

## Funcionalidades

- Cadastro e login com senha protegida por hash
- 16 salas com chat interno por partida
- Truco/retruco (1 → 3 → 6 → 9 → 12), correr, carta coberta, mão de 11 e
  mão de ferro
- Ranking global de vitórias e perfil do jogador
- Reconexão em caso de queda (janela de 60 s) e W.O. por abandono ou
  inatividade
- Interface com mouse: clique na carta para jogar, botões contextuais para
  as decisões

## Pré-requisitos

- Docker e Docker Compose
- Python 3.10+
- `python3-venv` (Ubuntu/Debian: `sudo apt install python3-venv`)
- `pygame` para o cliente: `pip install pygame`

## Como rodar

```bash
# Subir os servidores (Redis, PostgreSQL, Broker, Backend)
make up

# Abrir o cliente (um por jogador)
make cliente

# Jogar de outra máquina: apontar para o servidor
BROKER_HOST=<ip do servidor> make cliente

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

Todas as mensagens entre cliente, broker e backend são objetos JSON
delimitados por `\n` via TCP. A especificação completa está em
[DOCUMENTACAO.md](DOCUMENTACAO.md#3-interface-de-serviço-protocolo).

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

Testes cobrindo: lógica do jogo, Redis, PostgreSQL, servidor, broker e
cliente.

## Créditos dos assets

As imagens das cartas são do baralho padrão inglês publicado em domínio
público (CC0) no Wikimedia Commons.
