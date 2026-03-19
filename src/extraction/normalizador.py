"""Normalizador de campos extraídos: categorias, gêneros, público, horários."""

from __future__ import annotations

import re
from src.models.evento import Horario

# ── Mapeamento de categorias ──────────────────────────────────────

CATEGORIAS = {
    "show": [
        "show", "dj", "pocket show", "música", "musica", "jazz", "samba",
        "pagode", "choro", "cumbia", "forró", "funk", "hip hop", "rap",
        "mpb", "rock", "soul", "kizomba", "gafieira", "tributo",
        "discotecagem", "after", "festa", "ball", "grooving", "cortejo",
        "fanfrevo", "battle", "batalha", "mc ", "roda de ",
    ],
    "teatro": [
        "teatro", "espetáculo", "espetaculo", "peça", "peca",
        "cia.", "cia ", "companhia", "meretrizes", "geppetto",
        "mulher invisível", "protocolo grace", "meu corpo",
        "terceira margem", "faixa de graça", "lampião",
    ],
    "exposição": [
        "exposição", "exposicao", "exposições", "abertura exposição",
        "mural", "galeria", "instalação", "mostra de arte",
        "arte catarinense", "tapeçarias",
    ],
    "cinema": [
        "cinema", "sessão", "filme", "dir.", "min.", "min)",
        "cineclube", "mostra de cinema",
    ],
    "oficina": [
        "oficina", "workshop", "vivência", "vivencia",
    ],
    "visita_guiada": [
        "visita guiada", "visita mediada", "visitação", "tour cultural",
        "percurso guiado", "noite no museu",
    ],
    "circo": [
        "circo", "circenses", "manguecircus", "palhaça", "palhaço",
        "performance circense",
    ],
    "feira": [
        "feira", "feirarte",
    ],
    "literatura": [
        "roda de conversa", "livro", "leitura", "biblioteca",
        "crônicas", "canta, boró", "palavra percussiva",
    ],
    "dança": [
        "dança", "danca", "encantado", "lia rodrigues",
        "ballet", "balé",
    ],
    "arte_urbana": [
        "graffiti", "grafismo", "pintura mural", "laser mapping",
        "vj ", "street art",
    ],
    "infantil": [
        "maratoninha", "infantil", "crianças", "criancas",
        "boi de mamão", "brinca meu boi", "alivanta",
        "partimpim", "yeti", "monstro peludo",
        "para crianças", "atividades infantis",
    ],
    "gastronomia": [
        "bar", "restaurante", "gastrobar", "cachaçaria",
        "cervejaria", "pub", "boteco",
    ],
}

GENEROS = {
    "jazz": ["jazz", "freeda jazz", "sexta jazz"],
    "samba": ["samba", "pagode", "choro", "roda de choro", "gafieira"],
    "hip hop": ["hip hop", "rap", "mc ", "batalha", "break"],
    "mpb": ["mpb"],
    "rock": ["rock", "indie", "punk", "batalha de bandas"],
    "eletrônica": ["dj", "eletrônica", "techno", "house", "vibes", "dark surtado"],
    "soul/funk": ["soul", "funk", "groove", "grooving"],
    "forró": ["forró", "forro"],
    "cumbia": ["cumbia"],
    "world music": ["kizomba", "africano", "latina", "latinidades", "world"],
    "música popular": [
        "gondwana", "dazaranha", "joelma", "calcanhotto", "adriana calcanhotto",
    ],
}


def normalizar_horarios(horarios: list[Horario]) -> str:
    """Gera texto normalizado dos horários. Ex: '19:00', '10:00—17:00'."""
    partes = []
    for h in horarios:
        if h.fim:
            partes.append(f"{h.inicio}—{h.fim}")
        else:
            partes.append(h.inicio)
    return ", ".join(partes)


def classificar_categoria(titulo: str, descricao: str, nome_local: str) -> str:
    """Classifica a categoria do evento com base em título, descrição e local."""
    texto = f"{titulo} {descricao} {nome_local}".lower()
    nome_local_lower = nome_local.lower()

    # Ordem de prioridade (mais específico primeiro)
    for categoria, palavras in [
        ("cinema", CATEGORIAS["cinema"]),
        ("infantil", CATEGORIAS["infantil"]),
        ("oficina", CATEGORIAS["oficina"]),
        ("visita_guiada", CATEGORIAS["visita_guiada"]),
        ("circo", CATEGORIAS["circo"]),
        ("dança", CATEGORIAS["dança"]),
        ("teatro", CATEGORIAS["teatro"]),
        ("literatura", CATEGORIAS["literatura"]),
        ("arte_urbana", CATEGORIAS["arte_urbana"]),
        ("exposição", CATEGORIAS["exposição"]),
        ("feira", CATEGORIAS["feira"]),
        ("show", CATEGORIAS["show"]),
    ]:
        for palavra in palavras:
            if palavra in texto:
                return categoria

    # Gastronomia: usar word boundary e apenas no nome do local
    for palavra in CATEGORIAS["gastronomia"]:
        if re.search(rf"\b{re.escape(palavra)}\b", nome_local_lower):
            return "gastronomia"

    # Heurística final: se está em palco/arena/largo, provavelmente é show
    locais_show = ["palco", "arena", "largo", "calçadão"]
    if any(p in nome_local_lower for p in locais_show):
        return "show"

    return "outro"


def classificar_genero(titulo: str, descricao: str) -> str:
    """Classifica o gênero musical do evento."""
    texto = f"{titulo} {descricao}".lower()

    for genero, palavras in GENEROS.items():
        for palavra in palavras:
            if palavra in texto:
                return genero
    return ""


def classificar_publico(
    classificacao: str, titulo: str, descricao: str, secao: str
) -> str:
    """Classifica o público-alvo."""
    texto = f"{titulo} {descricao} {secao}".lower()
    classificacao_lower = classificacao.lower()

    # Infantil
    if any(
        p in texto
        for p in [
            "maratoninha", "infantil", "crianças", "criancas",
            "boi de mamão", "partimpim", "para todes",
        ]
    ):
        return "infantil"

    if classificacao_lower in ("livre", ""):
        if any(p in texto for p in ["infantil", "crianças", "brinca"]):
            return "infantil"
        return "família"

    if "18 anos" in classificacao_lower:
        return "adulto"

    # 10, 12, 14, 16 anos
    if re.search(r"\d{1,2}\s*anos", classificacao_lower):
        return "jovem/adulto"

    return "família"


def extrair_origem(texto: str) -> str:
    """Extrai cidade/estado de origem do artista."""
    # Padrão: "Florianópolis/SC", "Rio de Janeiro/RJ", "São Paulo/SP"
    match = re.search(
        r"([A-ZÀ-Ú][a-zà-ú]+(?:\s+(?:de|do|da|dos|das)\s+)?[A-ZÀ-Ú]?[a-zà-ú]*\s*/\s*[A-Z]{2})",
        texto,
    )
    if match:
        return match.group(1).strip()

    # Tenta padrão simplificado
    match = re.search(r"([A-Za-zÀ-ÿ\s]+/[A-Z]{2})", texto)
    if match:
        return match.group(1).strip()

    return ""


def extrair_info_adicional(texto: str) -> str:
    """Extrai informações como ingressos, vagas, etc."""
    infos = []

    # Ingressos
    match_ingresso = re.search(
        r"[Ii]ngresso[s]?[:\s]+(.+?)(?:\s*[-–—]|$)", texto
    )
    if match_ingresso:
        infos.append(f"Ingresso: {match_ingresso.group(1).strip()}")
    elif "gratuito" in texto.lower():
        infos.append("Ingresso: gratuito")
    elif "colaborativo" in texto.lower():
        infos.append("Ingresso: colaborativo")

    # Preço com R$
    match_preco = re.search(r"R\$\s*[\d,.]+", texto)
    if match_preco and "ingresso" not in " ".join(infos).lower():
        infos.append(match_preco.group(0))

    # Vagas
    match_vagas = re.search(r"(\d+)\s*vagas", texto, re.IGNORECASE)
    if match_vagas:
        infos.append(f"{match_vagas.group(1)} vagas")

    # Retirada de ingresso
    match_retirada = re.search(
        r"[Rr]etirada de ingresso[s]?\s+(.+?)(?:\s*[-–—]|$)", texto
    )
    if match_retirada:
        infos.append(f"Retirada: {match_retirada.group(1).strip()}")

    return " | ".join(infos)
