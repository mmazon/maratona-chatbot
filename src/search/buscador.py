"""Sistema de busca híbrida: vetorial (ChromaDB) + filtros Python."""

from __future__ import annotations

import chromadb
from src.models.evento import Evento


# Eventos destaque que devem sempre aparecer quando o contexto é relevante
DESTAQUES = {
    "21/03": [("JOELMA", "ARENA FLORIPA")],
    "22/03": [("MARISA MONTE", "ARENA FLORIPA")],
    "23/03": [("ADRIANA CALCANHOTTO", "MARATONINHA")],
}


class Buscador:
    """Busca híbrida: semântica + filtros estruturados."""

    def __init__(self, collection: chromadb.Collection, eventos: list[Evento]):
        self.collection = collection
        # Índice por ID para lookup rápido
        self._eventos_por_id: dict[str, Evento] = {e.id: e for e in eventos}

    def buscar(
        self,
        texto_query: str,
        filtros: dict | None = None,
        n_resultados: int = 15,
    ) -> list[tuple[Evento, float]]:
        """Busca eventos por texto + filtros estruturados.

        Args:
            texto_query: texto livre para busca semântica
            filtros: dict com filtros (data, bairro, categoria, etc.)
            n_resultados: número máximo de resultados

        Returns:
            Lista de (Evento, score) ordenada por relevância
        """
        filtros = filtros or {}

        # Se tem filtro de local específico, busca direta por local
        if filtros.get("local"):
            return self._buscar_por_local(filtros, n_resultados)

        # Monta filtros ChromaDB (where clause)
        where = self._montar_where(filtros)

        # Busca vetorial
        kwargs = {
            "query_texts": [texto_query],
            "n_results": min(n_resultados * 3, 100),  # busca mais, filtra depois
            "include": ["metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            resultados = self.collection.query(**kwargs)
        except Exception:
            # Se filtro falhar (ex: sem resultados), tenta sem filtro
            kwargs.pop("where", None)
            resultados = self.collection.query(**kwargs)

        if not resultados["ids"] or not resultados["ids"][0]:
            return []

        # Monta lista de resultados
        ids = resultados["ids"][0]
        distances = resultados["distances"][0]

        resultados_filtrados: list[tuple[Evento, float]] = []
        for id_evento, distancia in zip(ids, distances):
            evento = self._eventos_por_id.get(id_evento)
            if not evento:
                continue

            # Score: quanto menor a distância, melhor (cosine)
            score = 1.0 - distancia

            # Aplica filtros Python adicionais (mais flexíveis que ChromaDB)
            if filtros and not self._passa_filtros_python(evento, filtros):
                continue

            resultados_filtrados.append((evento, score))

        # Ordena por score
        resultados_filtrados.sort(key=lambda x: -x[1])

        # Se poucos resultados com filtros, tenta busca relaxada
        if len(resultados_filtrados) < 3 and filtros:
            resultados_relaxados = self._busca_relaxada(
                texto_query, filtros, n_resultados
            )
            # Adiciona resultados relaxados que não estão na lista
            ids_existentes = {e.id for e, _ in resultados_filtrados}
            for evento, score in resultados_relaxados:
                if evento.id not in ids_existentes:
                    # Penaliza um pouco o score por ser resultado relaxado
                    resultados_filtrados.append((evento, score * 0.8))
                    ids_existentes.add(evento.id)

            resultados_filtrados.sort(key=lambda x: -x[1])

        # Aplica preferência de local (ex: MARATONINHA para infantil)
        if filtros and filtros.get("preferir_local"):
            local_preferido = filtros["preferir_local"].upper()
            for i, (evento, score) in enumerate(resultados_filtrados):
                if local_preferido in evento.nome_local.upper():
                    # Boost de 30% para o local preferido
                    resultados_filtrados[i] = (evento, score * 1.3)
            resultados_filtrados.sort(key=lambda x: -x[1])

        # Injeta destaques do dia se relevantes e ausentes
        self._injetar_destaques(resultados_filtrados, filtros)

        return resultados_filtrados[:n_resultados]

    def _injetar_destaques(
        self,
        resultados: list[tuple[Evento, float]],
        filtros: dict,
    ):
        """Garante que eventos destaque apareçam nos resultados quando relevantes.

        Se o destaque já está nos resultados, dá boost no score.
        Se não está, injeta com score alto.
        """
        data = filtros.get("data", "")
        if not data or data not in DESTAQUES:
            return

        ids_existentes = {e.id for e, _ in resultados}

        for titulo_destaque, local_destaque in DESTAQUES[data]:
            # Já está nos resultados? Se sim, boost no score
            encontrado = False
            for i, (evento, score) in enumerate(resultados):
                if titulo_destaque.upper() in evento.titulo.upper():
                    resultados[i] = (evento, max(score, 1.5))
                    encontrado = True
                    break

            if encontrado:
                continue

            # Não está — busca e injeta
            for evento in self._eventos_por_id.values():
                if (
                    evento.data == data
                    and titulo_destaque.upper() in evento.titulo.upper()
                    and local_destaque.upper() in evento.nome_local.upper()
                    and evento.id not in ids_existentes
                ):
                    resultados.append((evento, 1.5))
                    break

        resultados.sort(key=lambda x: -x[1])

    def _buscar_por_local(
        self,
        filtros: dict,
        n_resultados: int,
    ) -> list[tuple[Evento, float]]:
        """Busca direta por nome de local — retorna todos os eventos do local.

        Ignora filtros de categoria/gênero pois o usuário quer ver TUDO do local.
        Mantém filtros de data, horário e período.
        """
        nome_local = filtros["local"].upper()
        # Filtros reduzidos: só data/horário, ignora categoria/gênero
        filtros_local = {
            k: v for k, v in filtros.items()
            if k in ("data", "periodo", "horario_min", "horario_max")
        }
        resultados: list[tuple[Evento, float]] = []

        for evento in self._eventos_por_id.values():
            # Match: nome exato ou contém o termo (ex: "CIC" match "TEATRO ADEMIR ROSA - CIC")
            if nome_local in evento.nome_local.upper():
                # Aplica apenas filtros de data/horário
                if filtros_local and not self._passa_filtros_python(evento, filtros_local):
                    continue
                # Score baseado em match exato vs parcial
                if evento.nome_local.upper() == nome_local:
                    score = 1.0
                else:
                    score = 0.9
                resultados.append((evento, score))

        # Ordena por data e horário
        resultados.sort(
            key=lambda x: (x[0].data, x[0].horario_inicio_minutos or 0)
        )
        return resultados[:n_resultados]

    def _busca_relaxada(
        self,
        texto_query: str,
        filtros: dict,
        n_resultados: int,
    ) -> list[tuple[Evento, float]]:
        """Busca com filtros relaxados quando a busca estrita retorna poucos resultados."""
        # Remove o filtro mais restritivo (gênero > categoria > bairro)
        filtros_relaxados = dict(filtros)
        for chave in ["genero", "categoria", "bairro"]:
            if chave in filtros_relaxados:
                filtros_relaxados.pop(chave)
                break

        where = self._montar_where(filtros_relaxados)
        kwargs = {
            "query_texts": [texto_query],
            "n_results": min(n_resultados * 2, 50),
            "include": ["metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            resultados = self.collection.query(**kwargs)
        except Exception:
            return []

        if not resultados["ids"] or not resultados["ids"][0]:
            return []

        resultado_list: list[tuple[Evento, float]] = []
        for id_evento, distancia in zip(resultados["ids"][0], resultados["distances"][0]):
            evento = self._eventos_por_id.get(id_evento)
            if not evento:
                continue
            if filtros and not self._passa_filtros_python(evento, filtros):
                continue
            resultado_list.append((evento, 1.0 - distancia))

        return resultado_list

    def _montar_where(self, filtros: dict) -> dict | None:
        """Monta cláusula where para ChromaDB."""
        condicoes = []

        if filtros.get("data"):
            condicoes.append({"data": filtros["data"]})

        if filtros.get("bairro"):
            condicoes.append({"bairro": filtros["bairro"].lower()})

        if filtros.get("categoria"):
            condicoes.append({"categoria": filtros["categoria"]})

        if filtros.get("genero"):
            condicoes.append({"genero": filtros["genero"]})

        if filtros.get("publico"):
            condicoes.append({"publico": filtros["publico"]})

        if not condicoes:
            return None
        if len(condicoes) == 1:
            return condicoes[0]
        return {"$and": condicoes}

    def _passa_filtros_python(self, evento: Evento, filtros: dict) -> bool:
        """Filtros mais complexos que ChromaDB não suporta."""
        # Filtro por horário mínimo (ex: "depois das 20h")
        if filtros.get("horario_min"):
            inicio = evento.horario_inicio_minutos
            if inicio is None:
                return False
            if inicio < filtros["horario_min"]:
                return False

        # Filtro por horário máximo (ex: "antes das 15h")
        if filtros.get("horario_max"):
            inicio = evento.horario_inicio_minutos
            if inicio is None:
                return False
            if inicio > filtros["horario_max"]:
                return False

        # Filtro por período (manhã, tarde, noite)
        if filtros.get("periodo"):
            inicio = evento.horario_inicio_minutos
            if inicio is None:
                return False
            periodo = filtros["periodo"]
            if periodo == "manhã" and not (6 * 60 <= inicio < 12 * 60):
                return False
            if periodo == "tarde" and not (12 * 60 <= inicio < 18 * 60):
                return False
            if periodo == "noite" and not (inicio >= 18 * 60):
                return False

        return True

    def buscar_por_roteiro(
        self,
        texto_query: str,
        filtros: dict | None = None,
        n_resultados: int = 8,
    ) -> list[tuple[Evento, float]]:
        """Busca eventos para montar um roteiro (itinerário).

        Para roteiros, relaxa os filtros de período (usa como horário mínimo)
        e busca mais amplamente para montar um itinerário completo.
        """
        filtros = dict(filtros or {})

        # Para roteiros, converte "periodo" em horário mínimo ao invés de filtro estrito
        # Ex: "tarde até noite" → começa às 12h, sem limite superior
        if filtros.get("periodo"):
            periodo = filtros.pop("periodo")
            if periodo == "manhã" and "horario_min" not in filtros:
                filtros["horario_min"] = 6 * 60
            elif periodo == "tarde" and "horario_min" not in filtros:
                filtros["horario_min"] = 12 * 60
            elif periodo == "noite" and "horario_min" not in filtros:
                filtros["horario_min"] = 18 * 60

        # Busca com filtros originais
        candidatos = self.buscar(texto_query, filtros, n_resultados=30)

        # Se poucos resultados, tenta sem categoria (muitos shows são "outro")
        if len(candidatos) < n_resultados and filtros.get("categoria"):
            filtros_sem_cat = {k: v for k, v in filtros.items() if k != "categoria"}
            candidatos_extra = self.buscar(texto_query, filtros_sem_cat, n_resultados=30)
            ids_existentes = {e.id for e, _ in candidatos}
            for evento, score in candidatos_extra:
                if evento.id not in ids_existentes:
                    candidatos.append((evento, score * 0.85))

        # Filtra eventos com horário definido
        com_horario = [(e, s) for e, s in candidatos if e.horario_inicio_minutos is not None]

        # Ordena por horário
        com_horario.sort(key=lambda x: x[0].horario_inicio_minutos or 0)

        # Remove sobreposições (greedy)
        roteiro: list[tuple[Evento, float]] = []
        ultimo_fim = 0
        for evento, score in com_horario:
            inicio = evento.horario_inicio_minutos or 0
            if inicio >= ultimo_fim:
                roteiro.append((evento, score))
                # Estima duração: se tem fim, usa; senão, estima 60min
                fim = evento.horario_fim_minutos
                if fim is None:
                    fim = inicio + 60
                ultimo_fim = fim

            if len(roteiro) >= n_resultados:
                break

        return roteiro
