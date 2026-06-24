import socket
import threading
import json
import os
import redis
import psycopg2

from jogo import Jogo, carta_str
import banco_redis as br
import banco_postgres as bp

# ------------------------------------------------------------------ #
#  Configurações                                                      #
# ------------------------------------------------------------------ #

HOST   = os.getenv('BACKEND_HOST', '0.0.0.0')
PORT   = int(os.getenv('BACKEND_PORT', 5001))
R_HOST = os.getenv('REDIS_HOST', 'redis')
R_PORT = int(os.getenv('REDIS_PORT', 6379))
PG_DSN = (
    f"host={os.getenv('PG_HOST','postgres')} "
    f"dbname={os.getenv('PG_DB','truco')} "
    f"user={os.getenv('PG_USER','truco')} "
    f"password={os.getenv('PG_PASS','truco')}"
)

TIMER_JOGAR     = 45   # segundos para jogar uma carta
TIMER_DECISAO   = 30   # segundos para qualquer outra decisão
TIMER_RECONEXAO = 60   # janela de reconexão
RODADAS_AFK_WO  = 2    # rodadas afk após reconexão para W.O.

# ------------------------------------------------------------------ #
#  Estado global                                                      #
# ------------------------------------------------------------------ #

_lock              = threading.Lock()
_salas             = {}
_timers_turno      = {}   # sala_id  -> threading.Timer
_timers_desconexao = {}   # nome     -> threading.Timer
_pg_lock           = threading.Lock()
_r                 = None
_pg                = None


def _sala_vazia(tipo, max_j):
    return {
        'tipo': tipo,
        'max': max_j,
        'jogadores': [],
        'conexoes': {},          # nome -> socket
        'jogo': None,
        'status': 'aguardando',
        'votos_correr': {},      # nome -> bool
        'afk_conta': {},         # nome -> int
        'ja_reconectou': set(),  # quem já usou a reconexão nesta partida
        'partida_id': None,
    }


def _inicializar_salas():
    for i in range(1, 14):
        _salas[i] = _sala_vazia('normal', 4)
    for i in range(14, 17):
        _salas[i] = _sala_vazia('1v1', 2)


# ------------------------------------------------------------------ #
#  Helpers de rede                                                    #
# ------------------------------------------------------------------ #

def enviar(conn, msg):
    try:
        conn.sendall((json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8'))
    except OSError:
        pass


def broadcast(sala_id, msg, exceto=None):
    with _lock:
        conexoes = dict(_salas[sala_id]['conexoes'])
    for nome, conn in conexoes.items():
        if nome != exceto:
            enviar(conn, msg)


def enviar_estado_todos(sala_id):
    with _lock:
        jogo = _salas[sala_id]['jogo']
        conexoes = dict(_salas[sala_id]['conexoes'])
        online = set(conexoes.keys())
    if jogo is None:
        return
    for nome, conn in conexoes.items():
        estado = montar_estado_para(jogo, nome, sala_id, online)
        enviar(conn, {'tipo': 'estado_jogo', 'dados': estado})


def montar_estado_para(jogo, nome, sala_id, online=None):
    """Monta o dict de estado do jogo para um jogador específico."""
    if online is None:
        with _lock:
            online = set(_salas[sala_id]['conexoes'].keys())

    jogadores = []
    for n in jogo.jogadores:
        jogadores.append({
            'nome': n,
            'dupla': jogo.duplas[n],
            'n_cartas': len(jogo.maos.get(n, [])),
            'vez': (jogo.status == 'jogando' and n == jogo.jogador_da_vez()),
            'online': n in online,
        })

    mesa = []
    for n, carta in jogo.rodada_atual:
        mesa.append({
            'jogador': n,
            'carta': carta_str(carta) if carta else '????',
            'coberta': carta is None,
        })

    # Mão de ferro: jogadores não veem suas próprias cartas
    if jogo.eh_mao_de_ferro():
        suas_cartas = ['????' for _ in jogo.maos.get(nome, [])]
    else:
        suas_cartas = [carta_str(c) for c in jogo.maos.get(nome, [])]

    return {
        'sala': sala_id,
        'tipo': jogo.tipo,
        'rodada_atual': len(jogo.resultados_rodadas) + 1,
        'mao_numero': jogo.mao_numero,
        'mao_valor': jogo.valor_mao,
        'valor_proposto': jogo.valor_proposto,
        'dupla_pediu_truco': jogo.dupla_pediu_truco,
        'vira': carta_str(jogo.vira) if jogo.vira else None,
        'placar': [jogo.placar[0], jogo.placar[1]],
        'suas_cartas': suas_cartas,
        'jogadores': jogadores,
        'mesa': mesa,
        'status': jogo.status,
        'mao_de_11': jogo.eh_mao_de_11(),
        'mao_de_ferro': jogo.eh_mao_de_ferro(),
    }


def info_salas():
    resultado = []
    with _lock:
        for sala_id, sala in _salas.items():
            resultado.append({
                'id': sala_id,
                'tipo': sala['tipo'],
                'jogadores': len(sala['jogadores']),
                'max': sala['max'],
                'status': sala['status'],
            })
    return resultado


# ------------------------------------------------------------------ #
#  Gerenciamento de salas                                             #
# ------------------------------------------------------------------ #

def entrar_sala(nome, sala_id, conn):
    if sala_id not in _salas:
        enviar(conn, {'tipo': 'erro', 'mensagem': 'Sala inválida'})
        return None

    with _lock:
        sala = _salas[sala_id]
        reconectando = (
            nome in sala['jogadores'] and
            nome not in sala['conexoes'] and
            br.esta_desconectado(_r, nome)
        )

        if reconectando:
            if nome in sala['ja_reconectou']:
                enviar(conn, {'tipo': 'erro', 'mensagem': 'Reconexão já utilizada nesta partida'})
                return None
            sala['conexoes'][nome] = conn
            sala['ja_reconectou'].add(nome)
            sala['afk_conta'].pop(nome, None)
            br.marcar_reconectado(_r, nome)
            br.remover_ttl_estado(_r, sala_id)

        elif nome in sala['jogadores']:
            enviar(conn, {'tipo': 'erro', 'mensagem': 'Você já está nesta sala'})
            return None

        elif sala['status'] == 'jogando':
            enviar(conn, {'tipo': 'erro', 'mensagem': 'Partida em andamento'})
            return None

        elif len(sala['jogadores']) >= sala['max']:
            enviar(conn, {'tipo': 'erro', 'mensagem': 'Sala cheia'})
            return None

        else:
            sala['jogadores'].append(nome)
            sala['conexoes'][nome] = conn
            br.entrar_sala(_r, sala_id, nome)
            reconectando = False

        deve_iniciar = (
            not reconectando and
            len(sala['jogadores']) == sala['max'] and
            sala['status'] == 'aguardando'
        )
        jogo = sala['jogo']

    # Cancelar timer de desconexão se reconectando
    if reconectando:
        _cancelar_timer_desconexao(nome)
        enviar(conn, {'tipo': 'ok', 'mensagem': 'Reconectado!'})
        broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} reconectou!'}, exceto=nome)
        if jogo:
            estado = montar_estado_para(jogo, nome, sala_id)
            enviar(conn, {'tipo': 'estado_jogo', 'dados': estado})
        # Retomar jogo se estava pausado esperando por este jogador
        with _lock:
            sala = _salas[sala_id]
            if sala['status'] == 'pausada' and jogo and jogo.jogador_da_vez() == nome:
                sala['status'] = 'jogando'
                jogo.status = 'jogando'
                _salvar_jogo(sala_id)
        broadcast(sala_id, {'tipo': 'aviso', 'mensagem': 'Jogo retomado!'})
        _iniciar_timer_turno(sala_id, nome, TIMER_DECISAO)
        return sala_id

    enviar(conn, {'tipo': 'ok', 'mensagem': f'Entrou na Sala {sala_id}'})
    broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} entrou na sala'}, exceto=nome)

    if deve_iniciar:
        _iniciar_jogo(sala_id)

    return sala_id


def sair_sala(nome, sala_id):
    with _lock:
        sala = _salas[sala_id]
        if nome not in sala['jogadores']:
            return
        em_jogo = sala['status'] in ('jogando', 'pausada')
        sala['conexoes'].pop(nome, None)
        if not em_jogo:
            sala['jogadores'].remove(nome)
            br.sair_sala(_r, sala_id, nome)

    broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} saiu da sala'})
    if em_jogo:
        _handle_desconexao(nome, sala_id)


def _iniciar_jogo(sala_id):
    with _lock:
        sala = _salas[sala_id]
        jogadores = list(sala['jogadores'])
        tipo = sala['tipo']

    jogo = Jogo(sala_id=sala_id, jogadores=jogadores, tipo=tipo)
    jogo.iniciar_mao()

    with _pg_lock:
        partida_id = bp.iniciar_partida(_pg, sala_id, tipo)

    with _lock:
        _salas[sala_id]['jogo'] = jogo
        _salas[sala_id]['status'] = 'jogando'
        _salas[sala_id]['partida_id'] = partida_id
        _salvar_jogo(sala_id)

    broadcast(sala_id, {'tipo': 'aviso', 'mensagem': 'Jogo iniciado!'})
    enviar_estado_todos(sala_id)
    primeiro = jogo.jogador_da_vez()
    _iniciar_timer_turno(sala_id, primeiro, TIMER_JOGAR)


def _salvar_jogo(sala_id):
    """Salva estado do jogo no Redis. Deve ser chamado com _lock."""
    jogo = _salas[sala_id]['jogo']
    if jogo:
        br.salvar_estado_jogo(_r, sala_id, jogo.para_dict())


# ------------------------------------------------------------------ #
#  Ações de jogo                                                      #
# ------------------------------------------------------------------ #

def _jogar_carta(nome, sala_id, indice, coberta):
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo is None or sala['status'] != 'jogando':
            return

    _cancelar_timer_turno(sala_id)
    resultado = jogo.jogar_carta(nome, indice, coberta=coberta)

    if not resultado['ok']:
        with _lock:
            conn = _salas[sala_id]['conexoes'].get(nome)
        if conn:
            enviar(conn, {'tipo': 'erro', 'mensagem': resultado['erro']})
        return

    with _lock:
        _salvar_jogo(sala_id)

    enviar_estado_todos(sala_id)
    _processar_resultado_acao(sala_id, resultado, jogo)


def _pedir_truco(nome, sala_id):
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo is None or sala['status'] != 'jogando':
            return

    _cancelar_timer_turno(sala_id)
    resultado = jogo.pedir_truco(nome)

    with _lock:
        conn = _salas[sala_id]['conexoes'].get(nome)

    if not resultado['ok']:
        if conn:
            enviar(conn, {'tipo': 'erro', 'mensagem': resultado.get('erro', '')})
        if resultado.get('jogo_encerrado'):
            with _lock:
                _salvar_jogo(sala_id)
            _encerrar_jogo(sala_id, resultado['dupla_vencedora_jogo'], 'completa')
        return

    with _lock:
        _salas[sala_id]['votos_correr'] = {}
        _salvar_jogo(sala_id)

    # Envia estado atualizado (status='truco_pendente') para todos os clientes
    # saberem que precisam responder ao truco
    enviar_estado_todos(sala_id)

    broadcast(sala_id, {
        'tipo': 'decisao_pendente',
        'acao': 'truco',
        'pedido_por': nome,
        'valor_proposto': resultado['valor_proposto'],
        'timer': TIMER_DECISAO,
    })

    # Timer para a equipe adversária responder
    with _lock:
        jogo = _salas[sala_id]['jogo']
        dupla_pediu = jogo.dupla_pediu_truco
        adversarios = [n for n in jogo.jogadores if jogo.duplas[n] != dupla_pediu]

    _iniciar_timer_turno(sala_id, adversarios[0], TIMER_DECISAO)


def _responder_truco(nome, sala_id, resposta):
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo is None or sala['status'] != 'jogando':
            return

    _cancelar_timer_turno(sala_id)
    resultado = jogo.responder_truco(nome, resposta)

    with _lock:
        conn = _salas[sala_id]['conexoes'].get(nome)

    if not resultado['ok']:
        if conn:
            enviar(conn, {'tipo': 'erro', 'mensagem': resultado['erro']})
        return

    with _lock:
        _salvar_jogo(sala_id)

    enviar_estado_todos(sala_id)
    _processar_resultado_acao(sala_id, resultado, jogo)


def _votar_correr(nome, sala_id, voto):
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo is None or sala['status'] not in ('jogando', 'truco_pendente'):
            return

        # Salas 1v1: decide sozinho
        if sala['tipo'] == '1v1':
            if not voto:
                enviar_estado_todos(sala_id)
                return
            resultado = jogo.responder_truco(nome, 'correr')
            _salvar_jogo(sala_id)
        else:
            # Sala normal: os dois da dupla precisam votar
            sala['votos_correr'][nome] = voto
            dupla = jogo.duplas[nome]
            parceiros = [n for n in jogo.jogadores if jogo.duplas[n] == dupla]
            votos = [sala['votos_correr'].get(n) for n in parceiros]

            if not all(v is not None for v in votos):
                # Ainda falta voto do parceiro
                parceiro = next(n for n in parceiros if n != nome)
                conn_parceiro = sala['conexoes'].get(parceiro)
                if conn_parceiro:
                    enviar(conn_parceiro, {
                        'tipo': 'decisao_pendente',
                        'acao': 'correr',
                        'timer': TIMER_DECISAO,
                    })
                _iniciar_timer_turno(sala_id, parceiro, TIMER_DECISAO)
                return

            sala['votos_correr'] = {}
            if not all(votos):
                # Algum não quis correr
                enviar_estado_todos(sala_id)
                return

            resultado = jogo.responder_truco(nome, 'correr')
            _salvar_jogo(sala_id)

    enviar_estado_todos(sala_id)
    _processar_resultado_acao(sala_id, resultado, jogo)


def _correr_mao_de_11(nome, sala_id):
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo is None or sala['status'] != 'jogando':
            return

    _cancelar_timer_turno(sala_id)
    resultado = jogo.correr_mao_de_11(nome)

    with _lock:
        conn = _salas[sala_id]['conexoes'].get(nome)

    if not resultado['ok']:
        if conn:
            enviar(conn, {'tipo': 'erro', 'mensagem': resultado['erro']})
        return

    with _lock:
        _salvar_jogo(sala_id)

    enviar_estado_todos(sala_id)
    _processar_resultado_acao(sala_id, resultado, jogo)


def _chat(nome, sala_id, mensagem):
    broadcast(sala_id, {'tipo': 'chat', 'de': nome, 'mensagem': mensagem})


def _processar_resultado_acao(sala_id, resultado, jogo):
    """Verifica se mão ou jogo encerrou após uma ação e age de acordo."""
    if resultado.get('jogo_encerrado'):
        _encerrar_jogo(sala_id, resultado['dupla_vencedora_jogo'], 'completa')
        return

    if resultado.get('mao_encerrada'):
        broadcast(sala_id, {
            'tipo': 'aviso',
            'mensagem': f"Mão encerrada! Dupla {resultado['dupla_vencedora_mao']} ganhou {resultado['pontos_ganhos']} ponto(s).",
        })
        # Pequena pausa para jogadores verem o resultado, depois inicia nova mão
        def nova_mao():
            with _lock:
                sala = _salas[sala_id]
                if sala['jogo'] is None:
                    return
                sala['jogo'].iniciar_mao()
                _salvar_jogo(sala_id)
                proximo = sala['jogo'].jogador_da_vez()
            enviar_estado_todos(sala_id)
            _iniciar_timer_turno(sala_id, proximo, TIMER_JOGAR)

        threading.Timer(3, nova_mao).start()
        return

    # Jogo continua: iniciar timer para próxima jogada
    if resultado.get('acao') == 'aceitar':
        proximo = jogo.jogador_da_vez()
        _iniciar_timer_turno(sala_id, proximo, TIMER_JOGAR)
    elif resultado.get('acao') == 'aumentar':
        # Adversário precisa responder
        with _lock:
            jogo = _salas[sala_id]['jogo']
            dupla_pediu = jogo.dupla_pediu_truco
            adversario = next(n for n in jogo.jogadores if jogo.duplas[n] != dupla_pediu)
        _iniciar_timer_turno(sala_id, adversario, TIMER_DECISAO)
    elif resultado.get('rodada_encerrada') and not resultado.get('mao_encerrada'):
        proximo = jogo.jogador_da_vez()
        _iniciar_timer_turno(sala_id, proximo, TIMER_JOGAR)
    elif 'rodada_encerrada' not in resultado:
        # Carta jogada, rodada não encerrou ainda
        proximo = jogo.jogador_da_vez()
        _iniciar_timer_turno(sala_id, proximo, TIMER_JOGAR)


# ------------------------------------------------------------------ #
#  Timers de turno                                                    #
# ------------------------------------------------------------------ #

def _iniciar_timer_turno(sala_id, nome, segundos):
    _cancelar_timer_turno(sala_id)
    broadcast(sala_id, {'tipo': 'timer_turno', 'jogador': nome, 'segundos': segundos})

    def timeout():
        _timeout_inatividade(sala_id, nome)

    t = threading.Timer(segundos, timeout)
    t.daemon = True
    with _lock:
        _timers_turno[sala_id] = t
    t.start()


def _cancelar_timer_turno(sala_id):
    with _lock:
        t = _timers_turno.pop(sala_id, None)
    if t:
        t.cancel()


# ------------------------------------------------------------------ #
#  Desconexão e reconexão                                             #
# ------------------------------------------------------------------ #

def _timeout_inatividade(sala_id, nome):
    """Chamado quando o timer de turno expira por inatividade."""
    with _lock:
        sala = _salas[sala_id]
        if nome not in sala['conexoes']:
            return  # já desconectado, tratado em outro lugar
        conn = sala['conexoes'].get(nome)

    # Desconectar por inatividade
    broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} foi removido por inatividade'})
    if conn:
        enviar(conn, {'tipo': 'erro', 'mensagem': 'Desconectado por inatividade'})
        try:
            conn.close()
        except OSError:
            pass
    _handle_desconexao(nome, sala_id)


def _handle_desconexao(nome, sala_id):
    """Trata a desconexão de um jogador durante uma partida."""
    with _lock:
        sala = _salas[sala_id]
        sala['conexoes'].pop(nome, None)
        jogo = sala['jogo']
        if jogo is None or sala['status'] == 'aguardando':
            # Fora do jogo: remove da sala
            if nome in sala['jogadores']:
                sala['jogadores'].remove(nome)
            br.sair_sala(_r, sala_id, nome)
            return

        # Adicionar TTL ao estado do jogo (janela de reconexão)
        br.registrar_desconexao(_r, nome, sala_id)
        br.definir_ttl_estado(_r, sala_id, TIMER_RECONEXAO)

    broadcast(sala_id, {
        'tipo': 'desconexao',
        'jogador': nome,
        'tempo_restante': TIMER_RECONEXAO,
    })

    # Timer: se não reconectar em 60s → W.O.
    def timeout_reconexao():
        _timeout_sem_reconexao(nome, sala_id)

    t = threading.Timer(TIMER_RECONEXAO, timeout_reconexao)
    t.daemon = True
    with _lock:
        _timers_desconexao[nome] = t
    t.start()

    # Se era a vez do jogador desconectado → pausar o jogo
    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        if jogo and jogo.jogador_da_vez() == nome and sala['status'] == 'jogando':
            sala['status'] = 'pausada'
            jogo.status = 'pausada'
            _salvar_jogo(sala_id)
            _cancelar_timer_turno(sala_id)
            broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'Jogo pausado aguardando {nome}...'})


def _cancelar_timer_desconexao(nome):
    with _lock:
        t = _timers_desconexao.pop(nome, None)
    if t:
        t.cancel()


def _timeout_sem_reconexao(nome, sala_id):
    """Jogador não reconectou a tempo → W.O."""
    with _lock:
        sala = _salas[sala_id]
        if nome not in sala['jogadores']:
            return
        jogo = sala['jogo']
        if jogo is None:
            return
        dupla_derrotada = jogo.duplas[nome]
        dupla_vencedora = 1 - dupla_derrotada

    broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} não reconectou. W.O.!'})
    _encerrar_jogo(sala_id, dupla_vencedora, 'wo')


def _verificar_afk_wo(nome, sala_id):
    """Verifica se o jogador (após reconexão) atingiu o limite de rodadas AFK."""
    with _lock:
        sala = _salas[sala_id]
        sala['afk_conta'][nome] = sala['afk_conta'].get(nome, 0) + 1
        count = sala['afk_conta'][nome]
        jogo = sala['jogo']
        if jogo is None:
            return False
        dupla_vencedora = 1 - jogo.duplas[nome]

    if count >= RODADAS_AFK_WO:
        broadcast(sala_id, {'tipo': 'aviso', 'mensagem': f'{nome} está AFK. W.O.!'})
        _encerrar_jogo(sala_id, dupla_vencedora, 'wo')
        return True
    return False


# ------------------------------------------------------------------ #
#  Encerramento de jogo                                               #
# ------------------------------------------------------------------ #

def _encerrar_jogo(sala_id, dupla_vencedora, motivo):
    _cancelar_timer_turno(sala_id)

    with _lock:
        sala = _salas[sala_id]
        jogo = sala['jogo']
        partida_id = sala['partida_id']
        jogadores = list(sala['jogadores'])
        conexoes = dict(sala['conexoes'])
        tipo = sala['tipo']
        max_j = sala['max']

        if jogo is None:
            return

    vencedores = [n for n in jogadores if jogo.duplas.get(n) == dupla_vencedora]
    perdedores  = [n for n in jogadores if jogo.duplas.get(n) != dupla_vencedora]

    with _pg_lock:
        if partida_id:
            bp.encerrar_partida(_pg, partida_id, vencedores, perdedores, motivo)
        for n in vencedores:
            bp.registrar_vitoria(_pg, n)
        for n in perdedores:
            bp.registrar_derrota(_pg, n)

    br.remover_estado_jogo(_r, sala_id)
    br.limpar_sala_jogadores(_r, sala_id)

    for n, conn in conexoes.items():
        resultado = 'vitoria' if n in vencedores else 'derrota'
        enviar(conn, {'tipo': 'fim_partida', 'resultado': resultado, 'motivo': motivo})

    with _lock:
        _salas[sala_id] = _sala_vazia(tipo, max_j)


# ------------------------------------------------------------------ #
#  Roteador de mensagens                                              #
# ------------------------------------------------------------------ #

def processar_mensagem(msg, nome, sala_id, conn):
    tipo = msg.get('tipo')

    if tipo == 'listar_salas':
        enviar(conn, {'tipo': 'salas', 'lista': info_salas()})

    elif tipo == 'meu_perfil':
        with _pg_lock:
            perfil = bp.obter_perfil(_pg, nome)
        if perfil:
            enviar(conn, {'tipo': 'perfil', **perfil})
        else:
            enviar(conn, {'tipo': 'erro', 'mensagem': 'Perfil não encontrado'})

    elif tipo == 'ranking':
        with _pg_lock:
            ranking = bp.obter_ranking(_pg)
        enviar(conn, {'tipo': 'ranking', 'lista': ranking})

    elif tipo == 'entrar_sala':
        sala_id = msg.get('sala')
        if not isinstance(sala_id, int):
            enviar(conn, {'tipo': 'erro', 'mensagem': 'Número de sala inválido'})
        else:
            sala_id = entrar_sala(nome, sala_id, conn)

    elif tipo == 'sair_sala':
        if sala_id:
            sair_sala(nome, sala_id)
            sala_id = None

    elif tipo == 'jogar_carta':
        if sala_id:
            _jogar_carta(nome, sala_id, msg.get('indice', 0), coberta=False)

    elif tipo == 'jogar_coberta':
        if sala_id:
            _jogar_carta(nome, sala_id, msg.get('indice', 0), coberta=True)

    elif tipo == 'pedir_truco':
        if sala_id:
            _pedir_truco(nome, sala_id)

    elif tipo == 'responder_truco':
        if sala_id:
            _responder_truco(nome, sala_id, msg.get('resposta'))

    elif tipo == 'votar_correr':
        if sala_id:
            _votar_correr(nome, sala_id, bool(msg.get('voto', False)))

    elif tipo == 'correr_mao_de_11':
        if sala_id:
            _correr_mao_de_11(nome, sala_id)

    elif tipo == 'chat':
        if sala_id:
            _chat(nome, sala_id, str(msg.get('mensagem', '')))

    else:
        enviar(conn, {'tipo': 'erro', 'mensagem': f'Tipo desconhecido: {tipo}'})

    return sala_id


# ------------------------------------------------------------------ #
#  Handler de conexão                                                 #
# ------------------------------------------------------------------ #

def handle_cliente(conn, addr):
    nome = None
    sala_id = None
    buffer = ''

    try:
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
                    msg = json.loads(linha)
                except json.JSONDecodeError:
                    continue

                nome = msg.get('usuario', nome)
                if nome:
                    sala_id = processar_mensagem(msg, nome, sala_id, conn)

    finally:
        if nome and sala_id:
            _handle_desconexao(nome, sala_id)


# ------------------------------------------------------------------ #
#  Inicialização                                                      #
# ------------------------------------------------------------------ #

def iniciar_servidor():
    global _r, _pg

    _r = redis.Redis(host=R_HOST, port=R_PORT, decode_responses=True)
    _pg = psycopg2.connect(PG_DSN)
    bp.criar_tabelas(_pg)
    _inicializar_salas()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen()
    print(f'Backend ouvindo em {HOST}:{PORT}')

    while True:
        conn, addr = srv.accept()
        t = threading.Thread(target=handle_cliente, args=(conn, addr), daemon=True)
        t.start()


if __name__ == '__main__':
    iniciar_servidor()
