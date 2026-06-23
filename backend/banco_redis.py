import json

# Assume que o cliente Redis é criado com decode_responses=True
# para que todas as respostas sejam strings (sem necessidade de .decode())

SESSAO_TTL      = 3600   # 1 hora
DESCONEXAO_TTL  = 60     # janela de reconexão em segundos


# ------------------------------------------------------------------ #
#  Chaves                                                             #
# ------------------------------------------------------------------ #

def _k_sessao(token):
    return f'sessao:{token}'

def _k_nome_token(nome):
    return f'token:{nome}'

def _k_sala_jogadores(sala_id):
    return f'sala:{sala_id}:jogadores'

def _k_sala_estado(sala_id):
    return f'sala:{sala_id}:estado'

def _k_desconexao(nome):
    return f'desconexao:{nome}'


# ------------------------------------------------------------------ #
#  Sessões                                                            #
# ------------------------------------------------------------------ #

def salvar_sessao(r, token, nome):
    """Salva sessão do jogador e índice reverso nome→token."""
    key = _k_sessao(token)
    r.hset(key, mapping={'nome': nome, 'sala': ''})
    r.expire(key, SESSAO_TTL)
    r.set(_k_nome_token(nome), token, ex=SESSAO_TTL)

def obter_sessao(r, token):
    """Retorna dict {nome, sala} ou None se não existir."""
    dados = r.hgetall(_k_sessao(token))
    return dados if dados else None

def atualizar_sessao_sala(r, token, sala_id):
    """Atualiza em qual sala o jogador está ('' se no lobby)."""
    valor = str(sala_id) if sala_id is not None else ''
    r.hset(_k_sessao(token), 'sala', valor)

def remover_sessao(r, token, nome=None):
    """Remove sessão e índice reverso."""
    r.delete(_k_sessao(token))
    if nome:
        r.delete(_k_nome_token(nome))

def token_por_nome(r, nome):
    """Retorna o token ativo do jogador ou None."""
    return r.get(_k_nome_token(nome))

def sessao_existe(r, token):
    return r.exists(_k_sessao(token)) > 0


# ------------------------------------------------------------------ #
#  Jogadores nas salas                                                #
# ------------------------------------------------------------------ #

def entrar_sala(r, sala_id, nome):
    r.sadd(_k_sala_jogadores(sala_id), nome)

def sair_sala(r, sala_id, nome):
    r.srem(_k_sala_jogadores(sala_id), nome)

def jogadores_na_sala(r, sala_id):
    return list(r.smembers(_k_sala_jogadores(sala_id)))

def num_jogadores_na_sala(r, sala_id):
    return r.scard(_k_sala_jogadores(sala_id))

def limpar_sala_jogadores(r, sala_id):
    r.delete(_k_sala_jogadores(sala_id))

def jogador_esta_na_sala(r, sala_id, nome):
    return bool(r.sismember(_k_sala_jogadores(sala_id), nome))


# ------------------------------------------------------------------ #
#  Estado do jogo (serializado como JSON)                             #
# ------------------------------------------------------------------ #

def salvar_estado_jogo(r, sala_id, estado_dict):
    r.set(_k_sala_estado(sala_id), json.dumps(estado_dict, ensure_ascii=False))

def obter_estado_jogo(r, sala_id):
    """Retorna o dict do estado do jogo ou None."""
    dados = r.get(_k_sala_estado(sala_id))
    return json.loads(dados) if dados else None

def remover_estado_jogo(r, sala_id):
    r.delete(_k_sala_estado(sala_id))

def estado_jogo_existe(r, sala_id):
    return r.exists(_k_sala_estado(sala_id)) > 0

def definir_ttl_estado(r, sala_id, segundos):
    """Define TTL no estado da sala (usado durante desconexão)."""
    r.expire(_k_sala_estado(sala_id), segundos)

def remover_ttl_estado(r, sala_id):
    """Remove TTL do estado (jogador reconectou, jogo retoma)."""
    r.persist(_k_sala_estado(sala_id))

def ttl_estado(r, sala_id):
    """Retorna o TTL em segundos (-1 = sem TTL, -2 = não existe)."""
    return r.ttl(_k_sala_estado(sala_id))


# ------------------------------------------------------------------ #
#  Desconexão                                                         #
# ------------------------------------------------------------------ #

def registrar_desconexao(r, nome, sala_id):
    """Registra desconexão com TTL de 60s. Expira = W.O."""
    key = _k_desconexao(nome)
    r.hset(key, mapping={'sala': str(sala_id), 'reconectou': '0'})
    r.expire(key, DESCONEXAO_TTL)

def esta_desconectado(r, nome):
    return r.exists(_k_desconexao(nome)) > 0

def obter_desconexao(r, nome):
    """Retorna dict {sala: int, reconectou: bool} ou None."""
    dados = r.hgetall(_k_desconexao(nome))
    if not dados:
        return None
    return {
        'sala': int(dados['sala']),
        'reconectou': dados['reconectou'] == '1',
    }

def marcar_reconectado(r, nome):
    """Marca que o jogador reconectou (dentro da janela de 60s)."""
    key = _k_desconexao(nome)
    if r.exists(key):
        r.hset(key, 'reconectou', '1')

def remover_desconexao(r, nome):
    r.delete(_k_desconexao(nome))

def tempo_restante_desconexao(r, nome):
    """Segundos restantes na janela de reconexão (-2 = expirou/não existe)."""
    return r.ttl(_k_desconexao(nome))
