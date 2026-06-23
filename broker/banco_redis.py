SESSAO_TTL = 3600  # 1 hora


def _k_sessao(token):
    return f'sessao:{token}'


def _k_nome_token(nome):
    return f'token:{nome}'


def salvar_sessao(r, token, nome):
    key = _k_sessao(token)
    r.hset(key, mapping={'nome': nome, 'sala': ''})
    r.expire(key, SESSAO_TTL)
    r.set(_k_nome_token(nome), token, ex=SESSAO_TTL)


def obter_sessao(r, token):
    dados = r.hgetall(_k_sessao(token))
    return dados if dados else None


def atualizar_sessao_sala(r, token, sala_id):
    valor = str(sala_id) if sala_id is not None else ''
    r.hset(_k_sessao(token), 'sala', valor)


def remover_sessao(r, token, nome=None):
    r.delete(_k_sessao(token))
    if nome:
        r.delete(_k_nome_token(nome))


def token_por_nome(r, nome):
    return r.get(_k_nome_token(nome))


def sessao_existe(r, token):
    return r.exists(_k_sessao(token)) > 0
