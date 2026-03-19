"""Parser estruturado para o PDF da Maratona Cultural.

Detecta:
- Cabeçalhos de dia (ex: "20/03" seguido de "SEXTA-FEIRA")
- Blocos de local (nome em maiúscula + endereço + classificação)
- Eventos dentro de cada bloco (horário + título + detalhes)
"""

from __future__ import annotations

import re
from src.models.evento import Evento, Horario
from src.extraction.normalizador import (
    normalizar_horarios,
    classificar_categoria,
    classificar_genero,
    classificar_publico,
    extrair_origem,
    extrair_info_adicional,
)

# ── Padrões Regex ──────────────────────────────────────────────────

# Cabeçalho de dia: "20/03" sozinho na linha ou "20/03\nSEXTA-FEIRA"
RE_DATA = re.compile(r"^(\d{2}/\d{2})\s*$")
RE_DIA_SEMANA = re.compile(
    r"^(SEGUNDA-FEIRA|TERÇA-FEIRA|QUARTA-FEIRA|QUINTA-FEIRA|"
    r"SEXTA-FEIRA|SÁBADO|DOMINGO)$"
)

# Separador de página/bloco do PDF: "20/03 -----..."
RE_SEPARADOR = re.compile(r"^\d{2}/\d{2}\s*-{5,}")

# Classificação: "Classificação: livre", "Classificação: 16 anos"
RE_CLASSIFICACAO = re.compile(r"Classificação:\s*(.+?)$", re.IGNORECASE)

# Horário no início de linha: "19h", "19h30", "10h—17h", "16h, 18h e 19h45"
RE_HORARIO_LINHA = re.compile(
    r"^(\d{1,2}[hH]\d{0,2}(?:\s*[—–-]\s*\d{1,2}[hH]\d{0,2})?)"
    r"(?:\s*(?:,\s*\d{1,2}[hH]\d{0,2})*(?:\s+e\s+\d{1,2}[hH]\d{0,2})?)"
)

# Qualquer menção de horário
RE_HORARIO = re.compile(r"\d{1,2}[hH]\d{0,2}")

# Intervalo de horário
RE_INTERVALO = re.compile(
    r"(\d{1,2}[hH]\d{0,2})\s*[—–-]\s*(\d{1,2}[hH]\d{0,2})"
)

# Múltiplos horários separados por vírgula e/ou "e"
RE_MULTI_HORARIO = re.compile(
    r"(\d{1,2}[hH]\d{0,2})(?:\s*,\s*(\d{1,2}[hH]\d{0,2}))*"
    r"(?:\s+e\s+(\d{1,2}[hH]\d{0,2}))?"
)

# Seções especiais
RE_SECAO = re.compile(
    r"^(PROGRAMAÇÃO OFF|EVENTOS PARCEIROS|MARATONINHA|"
    r"FEIRAS DA PREFEITURA MUNICIPAL DE FLORIANÓPOLIS.*?)$",
    re.IGNORECASE,
)

# Endereço — linhas que contêm referências de endereço comuns
RE_ENDERECO = re.compile(
    r"(Rua|Av\.|Avenida|Rod\.|Rodovia|Tv\.|Travessa|Praça|"
    r"SC-\d+|Sv\.|Servidão|Campus|Centro Integrado|Jardim|"
    r"Estacionamento|Victor Meirelles, \d|Parque\s)",
    re.IGNORECASE,
)


def _normalizar_hora(texto: str) -> str:
    """Converte '19h' → '19:00', '19h30' → '19:30', '9H30' → '09:30'."""
    texto = texto.strip().lower()
    match = re.match(r"(\d{1,2})h(\d{0,2})", texto)
    if not match:
        return texto
    hora = int(match.group(1))
    minuto = int(match.group(2)) if match.group(2) else 0
    return f"{hora:02d}:{minuto:02d}"


def _extrair_bairro(endereco: str) -> str:
    """Tenta extrair o bairro da linha de endereço.

    O bairro geralmente aparece antes de '- Classificação' e depois do último ' - '.
    Exemplos:
      'Rua Mal. Guilherme, 26 - Centro - Classificação: 16 anos' → 'Centro'
      'Centro Integrado de Cultura - Av. Gov. ..., 5600 - Agronômica' → 'Agronômica'
    """
    # Remove classificação
    limpo = re.sub(r"\s*-?\s*Classificação:.*$", "", endereco, flags=re.IGNORECASE)
    partes = [p.strip() for p in limpo.split(" - ") if p.strip()]
    if len(partes) >= 2:
        candidato = partes[-1]
        # Se o último segmento é curto e não parece endereço → é bairro
        # Também ignora fragmentos que não são bairros reais
        if (
            len(candidato) < 40
            and not re.match(r"\d", candidato)
            and "Classificação" not in candidato
            and "Anexo" not in candidato
            and "Café" not in candidato
        ):
            # Inclui referência de local conhecido no bairro
            # Ex: "Parque da Luz - Centro" → "Centro (Parque da Luz)"
            referencia = partes[0] if len(partes) >= 2 else ""
            if "Parque da Luz" in referencia:
                return f"{candidato} (Parque da Luz)"
            return candidato
    return ""


def _linha_e_local(linha: str) -> bool:
    """Heurística: linha é nome de local (maiúscula, sem horário no início).

    NÃO deve casar com títulos de eventos/exposições como:
    'MARATONA VISUAL: EXPOSIÇÃO CORPORALIDADE,'
    """
    linha = linha.strip()
    if not linha or len(linha) < 3:
        return False
    # Ignora separadores
    if RE_SEPARADOR.match(linha):
        return False
    # Ignora linhas de horário
    if RE_HORARIO.match(linha):
        return False
    # Ignora classificação isolada
    if linha.lower().startswith("classificação"):
        return False
    # Ignora linhas que são claramente títulos de evento/exposição
    palavras_evento = [
        "EXPOSIÇÃO", "EXPOSICAO", "MARATONA VISUAL", "CURADORIA",
        "MOSTRA ", "ABERTURA ", "SESSÃO", "OFICINA", "VISITA",
        "TOUR CULTURAL", "PROCISSÃO", "CORTEJO", "PINTURA MURAL",
        "RODA DE ", "PERCURSO",
    ]
    # Ignora avisos/disclaimers
    if "PROGRAMAÇÃO SUJEITA" in linha:
        return False
    for p in palavras_evento:
        if p in linha:
            return False
    # Ignora se termina com vírgula (continuação)
    if linha.endswith(","):
        return False
    # Ignora títulos de filmes (contêm duração como "16 min", "3'30''")
    if re.search(r"\d+\s*min\b", linha) or re.search(r"\d+'\d*''?", linha):
        return False
    # Ignora linhas que parecem créditos de filme ("de Fulano, XX min")
    if re.search(r",\s*de\s+[A-Z]", linha):
        return False
    # Nomes de locais não costumam ter "!" ou "?"
    if "!" in linha or "?" in linha:
        return False
    # Nome de local: predominantemente maiúscula
    letras = [c for c in linha if c.isalpha()]
    if not letras:
        return False
    proporcao_maiuscula = sum(1 for c in letras if c.isupper()) / len(letras)
    return proporcao_maiuscula > 0.7 and len(linha) > 3


def _extrair_horarios_da_linha(texto: str) -> tuple[list[Horario], str]:
    """Extrai horários do início de uma linha de evento.

    Retorna (lista de Horario, texto restante sem horários).
    """
    horarios: list[Horario] = []
    texto_original = texto.strip()

    # Primeiro, tenta intervalo: "10h—17h"
    intervalo = RE_INTERVALO.match(texto)
    if intervalo:
        inicio = _normalizar_hora(intervalo.group(1))
        fim = _normalizar_hora(intervalo.group(2))
        h = Horario(
            inicio=inicio,
            fim=fim,
            texto_original=intervalo.group(0),
        )
        horarios.append(h)
        resto = texto[intervalo.end():].strip()
        return horarios, resto

    # Tenta múltiplos horários: "16h, 18h e 19h45" ou "15h30 e 17h"
    todos_horarios = list(RE_HORARIO.finditer(texto))
    if todos_horarios:
        # Encontra até onde vai o bloco de horários
        ultimo_horario = todos_horarios[-1]
        bloco_horario_fim = ultimo_horario.end()

        # Verifica se há textos de ligação (", ", " e ") entre os horários
        bloco = texto[:bloco_horario_fim]

        # Se contém só horários + conectores, é bloco de múltiplos horários
        for match_h in todos_horarios:
            h_texto = match_h.group(0)
            h = Horario(
                inicio=_normalizar_hora(h_texto),
                fim=None,
                texto_original=h_texto,
            )
            horarios.append(h)

        resto = texto[bloco_horario_fim:].strip()
        return horarios, resto

    return horarios, texto_original


def _criar_evento(
    data: str,
    dia_semana: str,
    nome_local: str,
    endereco: str,
    bairro: str,
    classificacao: str,
    secao: str,
    linha_evento: str,
    linhas_extra: list[str],
) -> Evento | None:
    """Cria um Evento a partir das informações parseadas."""
    horarios, titulo = _extrair_horarios_da_linha(linha_evento)
    if not horarios:
        return None

    titulo = titulo.strip()
    if not titulo:
        return None

    # Monta texto bruto
    texto_bruto_partes = [linha_evento] + linhas_extra
    texto_bruto = "\n".join(texto_bruto_partes)

    # Descrição: linhas extras
    descricao = " ".join(linhas_extra).strip()

    # Texto completo para análise
    texto_completo = f"{titulo} {descricao}"

    # Informações adicionais (ingressos, vagas, etc.)
    info_adicional = extrair_info_adicional(texto_completo)

    # Origem (cidade/estado)
    origem = extrair_origem(texto_completo)

    # Classificação de categoria, gênero e público
    categoria = classificar_categoria(titulo, descricao, nome_local)
    genero = classificar_genero(titulo, descricao)
    publico = classificar_publico(classificacao, titulo, descricao, secao)

    # Tags automáticas
    tags = [t for t in [categoria, genero, publico, bairro.lower()] if t]
    if secao:
        tags.append(secao.lower())

    return Evento(
        data=data,
        dia_semana=dia_semana,
        horarios=horarios,
        texto_horario_original=normalizar_horarios(horarios),
        nome_local=nome_local,
        endereco=endereco,
        bairro=bairro,
        classificacao=classificacao,
        titulo=titulo,
        descricao=descricao,
        categoria=categoria,
        genero=genero,
        publico=publico,
        origem=origem,
        informacoes_adicionais=info_adicional,
        tags=tags,
        secao=secao,
        texto_bruto=texto_bruto,
    )


def parsear_programacao(texto: str) -> list[Evento]:
    """Parseia o texto completo da programação e retorna lista de Eventos."""
    linhas = texto.split("\n")
    eventos: list[Evento] = []

    # Estado do parser
    data_atual = ""
    dia_semana_atual = ""
    nome_local_atual = ""
    endereco_atual = ""
    bairro_atual = ""
    classificacao_atual = ""
    secao_atual = ""

    # Buffer para evento em construção
    linha_evento_atual: str | None = None
    linhas_extra_evento: list[str] = []

    # Buffer de linhas não classificadas (potenciais nomes de local)
    linhas_nao_classificadas: list[str] = []

    def _flush_evento():
        """Emite o evento em construção, se houver."""
        nonlocal linha_evento_atual, linhas_extra_evento
        if linha_evento_atual and nome_local_atual:
            ev = _criar_evento(
                data=data_atual,
                dia_semana=dia_semana_atual,
                nome_local=nome_local_atual,
                endereco=endereco_atual,
                bairro=bairro_atual,
                classificacao=classificacao_atual,
                secao=secao_atual,
                linha_evento=linha_evento_atual,
                linhas_extra=linhas_extra_evento,
            )
            if ev:
                eventos.append(ev)
        linha_evento_atual = None
        linhas_extra_evento = []

    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()

        # ── Linha vazia ──
        if not linha:
            i += 1
            continue

        # ── Separador de bloco "20/03 -----..." ──
        if RE_SEPARADOR.match(linha):
            _flush_evento()
            linhas_nao_classificadas = []
            # Pode ter texto colado ao separador: "20/03 ----10h—21h EXPOSIÇÃO..."
            pos_sep = linha.find("-")
            apos_tracos = re.sub(r"^[\d/\s]*-+", "", linha).strip()
            if apos_tracos and RE_HORARIO.match(apos_tracos):
                # Texto colado — trata como linha de evento no contexto atual
                linha_evento_atual = apos_tracos
                linhas_extra_evento = []
            i += 1
            continue

        # ── Cabeçalho de data ──
        match_data = RE_DATA.match(linha)
        if match_data:
            _flush_evento()
            data_atual = match_data.group(1)
            nome_local_atual = ""
            i += 1
            continue

        # ── Dia da semana ──
        if RE_DIA_SEMANA.match(linha):
            dia_semana_atual = linha
            i += 1
            continue

        # ── Seção especial ──
        if RE_SECAO.match(linha):
            _flush_evento()
            secao_atual = linha
            # Seções como MARATONINHA são também locais (têm endereço na próxima linha)
            # Reseta local para forçar re-detecção pelo endereço seguinte
            nome_local_atual = linha
            endereco_atual = ""
            bairro_atual = ""
            classificacao_atual = ""
            # Se "FEIRAS DA PREFEITURA..." pode ter próxima linha como continuação
            if linha.startswith("FEIRAS"):
                # Absorve linhas seguintes do mesmo cabeçalho
                while i + 1 < len(linhas):
                    prox = linhas[i + 1].strip()
                    if prox and prox.isupper() and not RE_HORARIO.match(prox) and not RE_SEPARADOR.match(prox):
                        secao_atual += " " + prox
                        nome_local_atual += " " + prox
                        i += 1
                    else:
                        break
            i += 1
            continue

        # ── Nome de local (maiúscula) ──
        if _linha_e_local(linha):
            # Verifica se não é continuação de título de evento
            if linha_evento_atual:
                # Se a linha anterior era um evento, e esta parece ser continuação
                # (ex: título de exposição em 2+ linhas)
                if not RE_ENDERECO.search(linha) and not RE_CLASSIFICACAO.search(linha):
                    # Pode ser continuação de título
                    # Heurística: se a próxima linha não-vazia é endereço,
                    # classificação, bairro curto ou horário → é novo local
                    prox = ""
                    for j in range(i + 1, min(i + 4, len(linhas))):
                        if linhas[j].strip():
                            prox = linhas[j].strip()
                            break
                    e_novo_local = (
                        RE_ENDERECO.search(prox)
                        or (prox and RE_CLASSIFICACAO.search(prox))
                        # Bairro curto como "Centro" sozinho na linha
                        or (prox and len(prox) < 25 and prox[0].isupper()
                            and not RE_HORARIO.match(prox)
                            and prox.replace(" ", "").isalpha())
                    )
                    if e_novo_local:
                        # É um novo local
                        _flush_evento()
                        nome_local_atual = linha
                        # Absorve linhas de continuação do nome
                        while i + 1 < len(linhas):
                            prox = linhas[i + 1].strip()
                            if prox and _linha_e_local(prox) and not RE_ENDERECO.search(prox):
                                nome_local_atual += " " + prox
                                i += 1
                            else:
                                break
                        endereco_atual = ""
                        bairro_atual = ""
                        classificacao_atual = ""
                        i += 1
                        continue
                    else:
                        # Continuação do evento anterior
                        linhas_extra_evento.append(linha)
                        i += 1
                        continue
            else:
                _flush_evento()
                nome_local_atual = linha
                # Absorve linhas de continuação do nome
                while i + 1 < len(linhas):
                    prox = linhas[i + 1].strip()
                    if (
                        prox
                        and _linha_e_local(prox)
                        and not RE_ENDERECO.search(prox)
                        and not RE_CLASSIFICACAO.search(prox)
                        and not RE_HORARIO.match(prox)
                    ):
                        nome_local_atual += " " + prox
                        i += 1
                    else:
                        break
                endereco_atual = ""
                bairro_atual = ""
                classificacao_atual = ""
                # Reseta seção se não é mais "PROGRAMAÇÃO OFF" etc.
                if secao_atual and not any(
                    s in secao_atual.upper()
                    for s in ["OFF", "PARCEIRO", "MARATONINHA", "FEIRA"]
                ):
                    secao_atual = ""
                i += 1
                continue

        # ── Endereço ──
        if RE_ENDERECO.search(linha) and not RE_HORARIO.match(linha):
            _flush_evento()
            # Se há linhas não classificadas antes do endereço,
            # provavelmente são o nome do novo local
            # Ex: "9 MOSTRA TRAÇO DE BOLSO\nA\nPraça Bento Silvério..."
            if linhas_nao_classificadas:
                candidato_local = " ".join(linhas_nao_classificadas)
                # Ignora se é aviso/disclaimer, não nome de local
                if "PROGRAMAÇÃO SUJEITA" not in candidato_local.upper():
                    nome_local_atual = candidato_local
                linhas_nao_classificadas = []
            endereco_atual = linha
            bairro_novo = _extrair_bairro(linha)
            if bairro_novo:
                bairro_atual = bairro_novo
            # Extrai classificação se presente na mesma linha
            match_class = RE_CLASSIFICACAO.search(linha)
            if match_class:
                classificacao_atual = match_class.group(1).strip()
            i += 1
            continue

        # ── Classificação em linha separada ──
        match_class = RE_CLASSIFICACAO.match(linha)
        if match_class:
            classificacao_atual = match_class.group(1).strip()
            i += 1
            continue

        # ── Linha de evento (começa com horário) ──
        if RE_HORARIO.match(linha):
            _flush_evento()
            linha_evento_atual = linha
            linhas_extra_evento = []
            i += 1
            continue

        # ── Linha de continuação (não começa com horário, não é local/endereço) ──
        if linha_evento_atual:
            # Antes de assumir continuação, verifica se a próxima linha
            # não-vazia é um endereço — nesse caso, esta linha é provavelmente
            # o nome de um novo local (ex: "9 MOSTRA TRAÇO DE BOLSO")
            prox_nao_vazia = ""
            for j in range(i + 1, min(i + 4, len(linhas))):
                if linhas[j].strip():
                    prox_nao_vazia = linhas[j].strip()
                    break
            if RE_ENDERECO.search(prox_nao_vazia) and not RE_HORARIO.match(prox_nao_vazia):
                _flush_evento()
                linhas_nao_classificadas = [linha]
            else:
                linhas_extra_evento.append(linha)
                linhas_nao_classificadas = []
        elif nome_local_atual and not endereco_atual:
            # Pode ser bairro avulso. Ex: "Centro" sozinho na linha
            # Validação: curto, sem duração, não é todo maiúscula (seria título)
            letras_linha = [c for c in linha if c.isalpha()]
            proporcao_upper = (
                sum(1 for c in letras_linha if c.isupper()) / len(letras_linha)
                if letras_linha else 0
            )
            if (
                len(linha) < 30
                and not RE_HORARIO.match(linha)
                and "min" not in linha.lower()
                and "'" not in linha
                and "," not in linha
                and linha[0].isupper()
                and proporcao_upper < 0.7  # bairros não são TUDO MAIÚSCULA
            ):
                # Limpa classificação se estiver colada ao bairro
                bairro_limpo = re.sub(
                    r"\s*-?\s*Classificação:.*$", "", linha, flags=re.IGNORECASE
                ).strip()
                if bairro_limpo:
                    bairro_atual = bairro_limpo
                    # Extrai classificação se presente
                    match_cl = RE_CLASSIFICACAO.search(linha)
                    if match_cl:
                        classificacao_atual = match_cl.group(1).strip()
            linhas_nao_classificadas = []
        else:
            # Linha não classificada — pode ser nome de local não reconhecido
            # Ex: "9 MOSTRA TRAÇO DE BOLSO", "A" (fragmentos de "9ª")
            linhas_nao_classificadas.append(linha)
        i += 1

    # Flush final
    _flush_evento()

    return eventos
