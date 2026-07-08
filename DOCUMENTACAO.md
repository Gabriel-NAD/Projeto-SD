# Truco Paulista Distribuído — Documentação

Documentação técnica do projeto desenvolvido para a disciplina de Sistemas
Distribuídos — UTFPR Campus Campo Mourão.

## Sumário

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Interface de Serviço (Protocolo)](#3-interface-de-serviço-protocolo)
4. [Documentação do Código](#4-documentação-do-código)
5. [Execução da Aplicação](#5-execução-da-aplicação)
6. [Aspectos de Sistemas Distribuídos](#6-aspectos-de-sistemas-distribuídos)
7. [Testes](#7-testes)

---

## 1. Visão Geral

O projeto implementa o jogo **Truco Paulista** multiplayer como um sistema
distribuído. Vários jogadores, cada um executando o cliente em sua própria
máquina, conectam-se a um servidor central que gerencia 16 salas de jogo:

| Salas | Tipo | Jogadores | Início da partida |
|-------|------|-----------|-------------------|
| 1 – 13 | Normal | 4 (2 duplas de 2) | ao completar 4 jogadores |
| 14 – 16 | 1v1 | 2 | ao completar 2 jogadores |

Funcionalidades: cadastro e login de usuários, salas com chat, partidas
completas de truco (truco/retruco, correr, mão de 11, mão de ferro, cartas
cobertas), ranking global de vitórias, perfil do jogador, reconexão em caso
de queda e W.O. por abandono ou inatividade.

---

## 2. Arquitetura

### 2.1. Diagrama

```
 máquina do jogador          │            servidor (Docker)
                             │
┌────────────────────┐       │   ┌──────────┐        ┌───────────┐
│  Cliente (pygame)  │◄──TCP:5000──►│  Broker  │◄──TCP:5001──►│  Backend  │
│ interface.py       │       │   │ broker.py│        │servidor.py│
│ cliente.py         │       │   └────┬─────┘        └─────┬─────┘
└────────────────────┘       │        │                    │
                             │        ▼                    ▼
                             │   ┌─────────┐         ┌────────────┐
                             │   │  Redis  │         │ PostgreSQL │
                             │   │  :6379  │         │   :5432    │
                             │   └─────────┘         └────────────┘
```

### 2.2. Componentes

| Componente | Onde roda | Porta | Papel |
|---|---|---|---|
| Cliente | máquina do jogador | — | interface gráfica (pygame) e comunicação com o broker |
| Broker | contêiner Docker | 5000 | autenticação, sessões e roteamento de mensagens |
| Backend | contêiner Docker | 5001 (rede interna) | lógica do jogo, salas, timers, reconexão |
| Redis | contêiner Docker | 6379 | estado volátil: sessões e partidas em andamento |
| PostgreSQL | contêiner Docker | 5432 | dados persistentes: usuários e histórico de partidas |

**Cliente** — dividido em dois módulos: `cliente.py` contém a classe
`Cliente`, responsável por toda a comunicação de rede (socket TCP, thread de
recepção, fila de mensagens) e pelo estado local; `interface.py` contém
apenas as telas pygame, que leem esse estado e enviam ações. Essa separação
permite testar a camada de rede sem abrir janela gráfica.

**Broker** — é o único ponto de entrada do sistema (única porta exposta no
`docker-compose.yml`). Faz o cadastro/login consultando o PostgreSQL, cria a
sessão do jogador no Redis (token) e, depois de autenticado, abre uma conexão
dedicada com o backend e passa a rotear mensagens nos dois sentidos. Antes de
repassar cada mensagem ao backend, **injeta o campo `"usuario"`** — o backend
confia no broker para a identidade do jogador, então o cliente nunca fala
diretamente com o backend.

**Backend** — mantém as 16 salas em memória, executa as regras do truco
(módulo `jogo.py`, sem nenhuma dependência de rede), controla os timers de
turno e de reconexão e grava os resultados no PostgreSQL. O estado de cada
partida é espelhado no Redis a cada jogada.

**Redis** — guarda apenas **estado volátil**: sessões ativas
(`sessao:{token}`), jogadores por sala (`sala:{id}:jogadores`), estado da
partida (`sala:{id}:estado`) e janelas de reconexão (`desconexao:{nome}`,
com TTL de 60 s).

**PostgreSQL** — guarda apenas **dados persistentes**: tabela `usuarios`
(nome, hash SHA-256 da senha, vitórias, partidas) e tabela `partidas`
(sala, tipo, vencedores, perdedores, status `completa`/`wo`, timestamps).
Derrotas são calculadas como `partidas - vitorias`.

### 2.3. Decisões de projeto

- **Broker separado do backend**: separa a preocupação de
  autenticação/sessão da lógica de jogo e cria um único ponto de entrada,
  deixando o backend inacessível de fora da rede Docker.
- **Regras do jogo puras**: `jogo.py` não conhece sockets nem banco — recebe
  jogadas e devolve resultados. Isso facilita os testes (a classe `Jogo` é
  testada isoladamente) e mantém o servidor enxuto.
- **Redis vs PostgreSQL**: estado de partida muda a cada jogada e morre com a
  partida (Redis, com TTL); dados de usuário precisam sobreviver a reinícios
  (PostgreSQL, com volume Docker).

---

## 3. Interface de Serviço (Protocolo)

- Transporte: **sockets TCP**.
- Formato: **JSON**, uma mensagem por linha (delimitador `\n`), UTF-8.
- O broker injeta `"usuario": "<nome>"` em toda mensagem repassada ao backend.

### 3.1. Mensagens do Cliente para o servidor

| Mensagem | Campos | Descrição |
|---|---|---|
| `registro` | `nome`, `senha` | cadastra usuário |
| `login` | `nome`, `senha` | autentica e recebe token de sessão |
| `logout` | — | encerra a sessão |
| `listar_salas` | — | pede a lista das 16 salas |
| `meu_perfil` | — | pede nome, partidas, vitórias e derrotas |
| `ranking` | — | pede o ranking global de vitórias |
| `entrar_sala` | `sala` | entra (ou reconecta) numa sala |
| `sair_sala` | — | sai da sala atual |
| `jogar_carta` | `indice` | joga a carta da posição indicada |
| `jogar_coberta` | `indice` | joga a carta virada para baixo |
| `pedir_truco` | — | propõe aumento do valor da mão |
| `responder_truco` | `resposta` | `aceitar`, `aumentar` ou `correr` |
| `votar_correr` | `voto` | voto da dupla para correr (sala normal) |
| `correr_mao_de_11` | — | corre da mão de 11 antes de jogar |
| `chat` | `mensagem` | mensagem para a sala atual |

### 3.2. Mensagens do servidor para o Cliente

| Mensagem | Campos principais | Descrição |
|---|---|---|
| `ok` | `mensagem`, `token`? | confirmação (o token só vem no login) |
| `erro` | `mensagem` | falha na operação |
| `salas` | `lista` | situação das 16 salas |
| `perfil` | `nome`, `partidas`, `vitorias`, `derrotas` | perfil do jogador |
| `ranking` | `lista` | ranking ordenado por vitórias |
| `estado_jogo` | `dados` | estado completo da partida (ver 3.3) |
| `aviso` | `mensagem` | eventos da sala (entrou, saiu, truco...) |
| `chat` | `de`, `mensagem` | mensagem de chat |
| `timer_turno` | `jogador`, `segundos` | início da contagem do turno |
| `decisao_pendente` | `acao`, `timer` | decisão aguardada (truco/correr) |
| `desconexao` | `jogador`, `tempo_restante` | jogador caiu; janela de reconexão |
| `fim_partida` | `resultado`, `motivo` | `vitoria`/`derrota`, `completa`/`wo` |

### 3.3. Estrutura do `estado_jogo`

O backend envia um estado **personalizado para cada jogador** (cada um só
enxerga as próprias cartas):

```json
{
  "sala": 3, "tipo": "normal",
  "rodada_atual": 2, "mao_numero": 5,
  "mao_valor": 3, "valor_proposto": null, "dupla_pediu_truco": null,
  "vira": "7♥", "placar": [6, 3],
  "suas_cartas": ["1♣", "K♠", "4♦"],
  "jogadores": [
    {"nome": "joao", "dupla": 0, "n_cartas": 2, "vez": true, "online": true}
  ],
  "mesa": [
    {"jogador": "maria", "carta": "3♣", "coberta": false},
    {"jogador": "pedro", "carta": "????", "coberta": true}
  ],
  "status": "jogando",
  "mao_de_11": false, "mao_de_ferro": false
}
```

Na **mão de ferro** (11 × 11) até as próprias cartas chegam como `"????"`.

### 3.4. Sessões e autenticação

1. O cliente envia `login`; o broker valida o hash da senha no PostgreSQL.
2. O broker gera um token (`uuid4`), salva a sessão no Redis e devolve o
   token no `ok`. Uma sessão anterior do mesmo usuário é invalidada
   (login único).
3. A cada mensagem seguinte o broker verifica se a sessão ainda existe no
   Redis antes de repassar ao backend.

---

## 4. Documentação do Código

### 4.1. Estrutura de pastas

```
Projeto-SD/
├── docker-compose.yml    # Redis, PostgreSQL, Backend e Broker
├── Makefile              # automação (venv, testes, containers, cliente)
├── README.md
├── DOCUMENTACAO.md
├── scripts/
│   └── info.py           # make info — estatísticas do servidor
├── frontend/
│   ├── cliente.py        # classe Cliente: rede e estado local
│   ├── interface.py      # telas pygame
│   ├── assets/cartas/    # sprites do baralho (domínio público)
│   ├── requirements.txt  # pygame
│   └── tests/
├── broker/
│   ├── broker.py         # autenticação, sessão e roteamento
│   ├── banco_postgres.py # registro/login (hash de senha)
│   ├── banco_redis.py    # sessões com token
│   ├── Dockerfile
│   └── tests/
└── backend/
    ├── servidor.py       # salas, timers, reconexão, W.O.
    ├── jogo.py           # regras puras do truco (sem rede)
    ├── banco_redis.py    # estado das partidas e desconexões
    ├── banco_postgres.py # usuários, partidas e ranking
    ├── Dockerfile
    └── tests/
```

### 4.2. `backend/jogo.py` — regras do truco

Funções puras: `criar_baralho()` (40 cartas — sem 8, 9, 10 e coringa),
`determinar_manilhas(vira)`, `forca_carta()`, `vencedor_rodada()`,
`vencedor_mao()`, `proximo_valor_truco()` (1 → 3 → 6 → 9 → 12).

Classe `Jogo`: mantém mãos, placar, rodadas e o fluxo da partida. Métodos
principais: `iniciar_mao()`, `jogar_carta()`, `pedir_truco()`,
`responder_truco()`, `correr_mao_de_11()`, `jogador_da_vez()`,
`eh_mao_de_11()`, `eh_mao_de_ferro()`. Os métodos `para_dict()`/`de_dict()`
serializam o jogo para o Redis.

### 4.3. `backend/servidor.py` — servidor do jogo

- **Uma thread por conexão** (`handle_cliente`), criada a cada `accept()`.
- Estado global das salas protegido por um `threading.RLock()`.
- `processar_mensagem()` roteia cada tipo de mensagem para a ação
  correspondente (`_jogar_carta`, `_pedir_truco`, `_votar_correr`...).
- **Timers** (`threading.Timer`): 45 s para jogar, 30 s para decisões,
  60 s de janela de reconexão. Timeout de turno derruba o jogador por
  inatividade; se ele já gastou a única reconexão, conta rodadas AFK e
  declara W.O. na segunda.
- `_handle_desconexao()` registra a queda no Redis (TTL 60 s), pausa o jogo
  se era a vez do jogador e agenda o W.O.; `entrar_sala()` detecta a volta
  do jogador e retoma a partida.
- `_encerrar_jogo()` grava vitórias/derrotas e a partida no PostgreSQL e
  reinicia a sala.

### 4.4. `broker/broker.py` — intermediário

`handle_cliente` trabalha em três fases: (1) só aceita `registro`/`login`;
(2) autenticado, abre a conexão dedicada com o backend; (3) roteia mensagens
do cliente para o backend (validando a sessão e injetando `usuario`) enquanto
uma segunda thread roteia as respostas do backend para o cliente. Se qualquer
uma das duas conexões cai, a outra é fechada junto, para que ambos os lados
percebam a queda.

### 4.5. `frontend/cliente.py` — camada de rede do cliente

Classe `Cliente`: conecta ao broker, mantém uma **thread de recepção** que
alimenta uma `queue.Queue`, e `processar_fila()` consome as mensagens
atualizando o estado local (`tela`, `estado_jogo`, `chat_msgs`,
`status_msg`...). `reconectar()` implementa a rota padrão de reconexão:
reabre o socket, refaz o login com as credenciais guardadas em memória e
tenta voltar para a sala em que o jogador estava.

### 4.6. `frontend/interface.py` — telas pygame

Janela fixa 1280×720, controle por mouse e teclado. Cada tela é uma função
com o próprio laço de eventos/desenho (`tela_inicio`, `tela_formulario`,
`tela_lobby`, `tela_salas`, `tela_espera_sala`, `tela_perfil`,
`tela_ranking`, `tela_jogo`, `tela_desconectado`), e `main()` despacha para a
tela indicada por `cliente.tela`. Widgets próprios (`Botao`, `CampoTexto`) e
sprites do baralho carregados de `assets/cartas/` (imagens de domínio
público — baralho padrão inglês). `arquivo_carta()` converte a carta do
protocolo (`"7♥"`) no nome do sprite (`7_of_hearts.png`).

### 4.7. `scripts/info.py`

Conecta direto ao Redis e ao PostgreSQL e imprime: jogadores cadastrados,
partidas registradas, sessões ativas e salas com partida em andamento.

---

## 5. Execução da Aplicação

### 5.1. Pré-requisitos

- Docker e Docker Compose
- Python 3.10+
- `python3-venv` (para os testes: `sudo apt install python3-venv`)
- `pygame` para o cliente: `pip install pygame`

### 5.2. Passo a passo

```bash
# 1. Subir a infraestrutura (Redis, PostgreSQL, Backend, Broker)
make up

# 2. Abrir um cliente por jogador (em terminais/máquinas diferentes)
make cliente

# 3. Estatísticas do servidor a qualquer momento
make info

# 4. Encerrar
make down          # derruba os containers
make reset-db      # derruba, apaga o banco e sobe de novo
```

Para jogar em máquinas diferentes, exporte o endereço do servidor antes de
abrir o cliente: `BROKER_HOST=<ip do servidor> make cliente`.

Fluxo no cliente: **Cadastro → Login → Ver Salas → clicar numa sala**.
A partida começa quando a sala completa (4 jogadores nas salas 1–13,
2 nas salas 14–16). Na partida: clicar na carta para jogar, botões para
truco/correr/coberta, campo de chat à direita.

---

## 6. Aspectos de Sistemas Distribuídos

Roteiro prático para demonstrar cada aspecto:

### 6.1. Comunicação entre processos (sockets TCP)

Quatro processos independentes (cliente, broker, backend e os bancos) se
comunicam exclusivamente por rede. Para visualizar:

```bash
make logs                    # broker e backend logando as conexões
docker compose ps            # um processo por contêiner
```

Abra 2+ clientes e observe as mensagens de chat atravessando
cliente → broker → backend → broker → clientes da sala.

### 6.2. Concorrência

- O broker e o backend criam **uma thread por conexão**; várias salas jogam
  simultaneamente sem interferência (o estado global é protegido por lock
  reentrante no backend).
- **Demonstração**: abra 4 clientes e inicie uma partida na sala 1 e outra
  na sala 14 ao mesmo tempo; as duas correm em paralelo no mesmo backend.

### 6.3. Estado compartilhado e persistência

- **Demonstração Redis**: durante uma partida, rode
  `docker exec -it projeto-sd-redis-1 redis-cli KEYS '*'` e inspecione
  `HGETALL sala:1:estado` — o estado espelhado a cada jogada.
- **Demonstração PostgreSQL**: ao fim de uma partida,
  `make info` mostra o total de partidas, e o ranking no lobby do cliente
  reflete as vitórias gravadas.

### 6.4. Tolerância a falhas

- **Queda de jogador**: feche a janela de um cliente no meio da partida.
  Os demais recebem o aviso de desconexão com contagem de 60 s; o jogo pausa
  somente quando chegar a vez do ausente. Reabra o cliente, faça login e
  entre na mesma sala dentro da janela: a partida **retoma do ponto em que
  estava** (estado recuperado, mesmas cartas). O cliente também oferece o
  botão **Reconectar**, que refaz login e reentra na sala sozinho.
- **W.O.**: deixe os 60 s expirarem — a dupla adversária vence por W.O. e o
  resultado é gravado no PostgreSQL com status `wo`.
- **Inatividade**: fique 45 s sem jogar — o servidor remove o jogador por
  inatividade e abre a mesma janela de reconexão, sem afetar as demais salas.
- **Limite**: cada jogador tem direito a **1 reconexão por partida**.

### 6.5. Sessões e autenticação distribuída

Faça login com o mesmo usuário em dois clientes: o segundo login invalida a
sessão do primeiro (token único por usuário no Redis). Senhas nunca circulam
nem são armazenadas em claro (hash SHA-256 no PostgreSQL).

### 6.6. Transparência de localização

O cliente só conhece `BROKER_HOST:5000`. Backend, Redis e PostgreSQL ficam
na rede interna do Docker, invisíveis para o jogador — a porta do backend
nem é exposta no `docker-compose.yml`.

---

## 7. Testes

```bash
make test    # cria o venv na primeira vez e roda toda a suíte
```

A suíte cobre a lógica do jogo (`jogo.py`), o servidor (salas, timers,
desconexão dupla, reconexão), os módulos de banco (Redis com fakeredis,
PostgreSQL com mocks), o broker (autenticação, sessões, queda do backend) e
o cliente (processamento de mensagens, detecção de queda, rota de
reconexão, mapeamento carta→sprite). Os testes de rede usam
`socket.socketpair()` para simular conexões reais sem subir servidores.
