"""Interpretador de queries em PT-BR.

Transforma perguntas naturais como:
  "Quero shows de hip hop no Centro hoje à noite"
em filtros estruturados:
  {categoria: "show", genero: "hip hop", bairro: "centro", data: "20/03", periodo: "noite"}
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Mapeamentos PT-BR ──────────────────────────────────────────────

MAPA_BAIRROS = {
    "centro": "centro",
    "agronômica": "agronômica",
    "agronomica": "agronômica",
    "trindade": "trindade",
    "lagoa": "lagoa da conceição",
    "lagoa da conceição": "lagoa da conceição",
    "lagoa da conceicao": "lagoa da conceição",
    "campeche": "campeche",
    "coqueiros": "coqueiros",
    "ingleses": "ingleses",
    "canasvieiras": "canasvieiras",
    "rio tavares": "rio tavares",
    "saco grande": "saco grande",
    "sambaqui": "sambaqui",
    "santo antônio": "santo antônio de lisboa",
    "santo antonio": "santo antônio de lisboa",
    "santo antônio de lisboa": "santo antônio de lisboa",
    "itaguaçu": "itaguaçu",
    "carvoeira": "carvoeira",
    "joão paulo": "joão paulo",
    "saco dos limões": "saco dos limões",
    "estreito": "estreito",
    "cidade universitária": "cidade universitária",
}

MAPA_CATEGORIAS = {
    "show": "show",
    "shows": "show",
    "música": "show",
    "musica": "show",
    "musical": "show",
    "musicais": "show",
    "teatro": "teatro",
    "peça": "teatro",
    "peças": "teatro",
    "espetáculo": "teatro",
    "espetáculos": "teatro",
    "exposição": "exposição",
    "exposições": "exposição",
    "expo": "exposição",
    "mostra": "exposição",
    "cinema": "cinema",
    "filme": "cinema",
    "filmes": "cinema",
    "oficina": "oficina",
    "oficinas": "oficina",
    "workshop": "oficina",
    "feira": "feira",
    "feiras": "feira",
    "visita": "visita_guiada",
    "tour": "visita_guiada",
    "circo": "circo",
    "dança": "dança",
    "infantil": "infantil",
    "criança": "infantil",
    "crianças": "infantil",
    "kids": "infantil",
    "literatura": "literatura",
    "livro": "literatura",
    "bar": "gastronomia",
    "bares": "gastronomia",
    "restaurante": "gastronomia",
    "gastronomia": "gastronomia",
}

MAPA_GENEROS = {
    "jazz": "jazz",
    "samba": "samba",
    "pagode": "samba",
    "choro": "samba",
    "hip hop": "hip hop",
    "hip-hop": "hip hop",
    "hiphop": "hip hop",
    "rap": "hip hop",
    "mpb": "mpb",
    "rock": "rock",
    "eletrônica": "eletrônica",
    "eletronica": "eletrônica",
    "dj": "eletrônica",
    "soul": "soul/funk",
    "funk": "soul/funk",
    "forró": "forró",
    "forro": "forró",
    "cumbia": "cumbia",
}

MAPA_PERIODOS = {
    "manhã": "manhã",
    "manha": "manhã",
    "de manhã": "manhã",
    "pela manhã": "manhã",
    "tarde": "tarde",
    "à tarde": "tarde",
    "de tarde": "tarde",
    "pela tarde": "tarde",
    "noite": "noite",
    "à noite": "noite",
    "de noite": "noite",
    "pela noite": "noite",
    "madrugada": "noite",
}

# Mapa de dias da semana para as datas do evento (20-23/03)
MAPA_DIAS_SEMANA = {
    "sexta": "20/03",
    "sexta-feira": "20/03",
    "sábado": "21/03",
    "sabado": "21/03",
    "domingo": "22/03",
    "segunda": "23/03",
    "segunda-feira": "23/03",
}


# Mapa de locais conhecidos (termos de busca → nomes no índice)
MAPA_LOCAIS = {
    "cic": "CIC",
    "teatro do cic": "TEATRO ADEMIR ROSA - CIC",
    "teatro ademir rosa": "TEATRO ADEMIR ROSA - CIC",
    "ademir rosa": "TEATRO ADEMIR ROSA - CIC",
    "hall do cic": "HALL DO CIC",
    "masc": "MASC - CIC",
    "museu de arte": "MASC - CIC",
    "museu da imagem e do som": "MUSEU DA IMAGEM E DO SOM - CIC",
    "mis": "MUSEU DA IMAGEM E DO SOM - CIC",
    "sala de cinema do cic": "SALA DE CINEMA GILBERTO GERLACH - CIC",
    "arena floripa": "ARENA FLORIPA",
    "arena": "ARENA FLORIPA",
    "tac": "TEATRO ÁLVARO DE CARVALHO",
    "teatro álvaro de carvalho": "TEATRO ÁLVARO DE CARVALHO",
    "teatro alvaro de carvalho": "TEATRO ÁLVARO DE CARVALHO",
    "sesc prainha": "TEATRO DO SESC PRAINHA",
    "teatro da ubro": "TEATRO DA UBRO",
    "ubro": "TEATRO DA UBRO",
    "escadaria do rosário": "ESCADARIA DO ROSÁRIO",
    "escadaria do rosario": "ESCADARIA DO ROSÁRIO",
    "miramar": "MIRAMAR",
    "palco centro leste": "PALCO CENTRO LESTE",
    "maratoninha": "MARATONINHA",
    "mercado público": "MERCADO PÚBLICO",
    "mercado publico": "MERCADO PÚBLICO",
    "largo da alfândega": "LARGO DA ALFÂNDEGA",
    "largo da alfandega": "LARGO DA ALFÂNDEGA",
    "museu de florianópolis": "MUSEU DE FLORIANÓPOLIS",
    "museu de florianopolis": "MUSEU DE FLORIANÓPOLIS",
    "museu victor meirelles": "MUSEU VICTOR MEIRELLES",
}


@dataclass
class QueryParseada:
    """Resultado do parsing de uma query do usuário."""

    texto_original: str
    texto_busca: str  # texto limpo para busca semântica
    filtros: dict = field(default_factory=dict)
    intencao: str = "busca"  # "busca", "roteiro", "informacao"
    busca_ampla: bool = False  # True quando poucos filtros — sugerir refinamento

    def descricao_filtros(self) -> str:
        """Descreve os filtros aplicados em PT-BR."""
        partes = []
        if self.filtros.get("local"):
            partes.append(f"local: {self.filtros['local']}")
        if self.filtros.get("data"):
            partes.append(f"data: {self.filtros['data']}")
        if self.filtros.get("bairro"):
            partes.append(f"bairro: {self.filtros['bairro']}")
        if self.filtros.get("categoria"):
            partes.append(f"categoria: {self.filtros['categoria']}")
        if self.filtros.get("genero"):
            partes.append(f"gênero: {self.filtros['genero']}")
        if self.filtros.get("publico"):
            partes.append(f"público: {self.filtros['publico']}")
        if self.filtros.get("periodo"):
            partes.append(f"período: {self.filtros['periodo']}")
        if self.filtros.get("horario_min"):
            h = self.filtros["horario_min"] // 60
            m = self.filtros["horario_min"] % 60
            partes.append(f"depois das {h:02d}:{m:02d}")
        if self.filtros.get("horario_max"):
            h = self.filtros["horario_max"] // 60
            m = self.filtros["horario_max"] % 60
            partes.append(f"antes das {h:02d}:{m:02d}")
        return ", ".join(partes) if partes else "sem filtros específicos"


def parsear_query(texto: str) -> QueryParseada:
    """Parseia uma query em PT-BR e extrai filtros estruturados."""
    texto_lower = texto.lower().strip()
    filtros: dict = {}
    texto_busca = texto

    # ── Intenção ──
    intencao = "busca"
    if any(p in texto_lower for p in ["roteiro", "itinerário", "itinerario", "sugerir roteiro", "montar roteiro"]):
        intencao = "roteiro"
    elif any(p in texto_lower for p in ["o que tem", "o que acontece", "programação", "agenda"]):
        intencao = "informacao"

    # ── Data ──
    # Dia da semana
    for dia_nome, dia_data in MAPA_DIAS_SEMANA.items():
        if dia_nome in texto_lower:
            filtros["data"] = dia_data
            break

    # Data explícita: "20/03", "dia 20", "dia 21/03"
    match_data = re.search(r"(?:dia\s+)?(\d{1,2})/(\d{2})", texto_lower)
    if match_data:
        dia = int(match_data.group(1))
        mes = match_data.group(2)
        filtros["data"] = f"{dia:02d}/{mes}"
    else:
        match_dia = re.search(r"dia\s+(\d{1,2})", texto_lower)
        if match_dia:
            dia = int(match_dia.group(1))
            filtros["data"] = f"{dia:02d}/03"

    # ── Bairro ──
    for bairro_input, bairro_normalizado in sorted(
        MAPA_BAIRROS.items(), key=lambda x: -len(x[0])
    ):
        # Usa word boundary para evitar matches parciais
        if re.search(rf"\b{re.escape(bairro_input)}\b", texto_lower):
            filtros["bairro"] = bairro_normalizado
            break

    # ── Local específico ──
    for local_input, local_normalizado in sorted(
        MAPA_LOCAIS.items(), key=lambda x: -len(x[0])
    ):
        if local_input in texto_lower:
            filtros["local"] = local_normalizado
            break

    # ── Categoria ──
    for cat_input, cat_normalizada in sorted(
        MAPA_CATEGORIAS.items(), key=lambda x: -len(x[0])
    ):
        if re.search(rf"\b{re.escape(cat_input)}\b", texto_lower):
            filtros["categoria"] = cat_normalizada
            break

    # ── Gênero musical ──
    for gen_input, gen_normalizado in sorted(
        MAPA_GENEROS.items(), key=lambda x: -len(x[0])
    ):
        if re.search(rf"\b{re.escape(gen_input)}\b", texto_lower):
            filtros["genero"] = gen_normalizado
            break

    # ── Público ──
    if any(p in texto_lower for p in ["infantil", "criança", "crianças", "kids", "pra criança"]):
        filtros["publico"] = "infantil"
    elif "família" in texto_lower or "familia" in texto_lower:
        filtros["publico"] = "família"

    # ── Período ──
    for periodo_input, periodo_normalizado in sorted(
        MAPA_PERIODOS.items(), key=lambda x: -len(x[0])
    ):
        if periodo_input in texto_lower:
            filtros["periodo"] = periodo_normalizado
            break

    # ── Horário específico ──
    # "depois das 20h", "após as 18h"
    match_depois = re.search(
        r"(?:depois|após|a partir)\s+d[aeo]s?\s+(\d{1,2})[hH](\d{0,2})",
        texto_lower,
    )
    if match_depois:
        h = int(match_depois.group(1))
        m = int(match_depois.group(2)) if match_depois.group(2) else 0
        filtros["horario_min"] = h * 60 + m

    # "antes das 15h"
    match_antes = re.search(
        r"(?:antes|até)\s+[àa]?s?\s+(\d{1,2})[hH](\d{0,2})",
        texto_lower,
    )
    if match_antes:
        h = int(match_antes.group(1))
        m = int(match_antes.group(2)) if match_antes.group(2) else 0
        filtros["horario_max"] = h * 60 + m

    # ── Gera texto de busca limpo ──
    # Remove termos de filtro do texto para a busca semântica ser mais efetiva
    texto_busca = texto_lower
    for remover in [
        "quero", "me sugere", "me indica", "me recomenda", "o que tem",
        "tem algo", "o que acontece", "procuro", "busco",
        "no centro", "na lagoa", "no campeche", "na trindade",
        "hoje", "amanhã", "à noite", "à tarde", "de manhã",
        "pra criança", "para crianças", "infantil",
        "depois das", "antes das", "a partir das",
    ]:
        texto_busca = texto_busca.replace(remover, "")
    texto_busca = re.sub(r"\s+", " ", texto_busca).strip()

    # Se o texto ficou vazio, usa o original
    if len(texto_busca) < 3:
        texto_busca = texto

    # ── Preferência: infantil sem bairro → priorizar MARATONINHA ──
    if filtros.get("publico") == "infantil" and "bairro" not in filtros:
        filtros["preferir_local"] = "MARATONINHA"

    # ── Detectar busca ampla (poucos filtros) para sugerir refinamento ──
    filtros_ativos = [
        k for k in ["data", "bairro", "categoria", "genero", "periodo",
                     "horario_min", "horario_max"]
        if k in filtros
    ]
    busca_ampla = len(filtros_ativos) < 2

    return QueryParseada(
        texto_original=texto,
        texto_busca=texto_busca,
        filtros=filtros,
        intencao=intencao,
        busca_ampla=busca_ampla,
    )
