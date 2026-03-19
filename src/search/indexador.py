"""Indexa eventos no ChromaDB para busca vetorial."""

from __future__ import annotations

import chromadb
from src.models.evento import Evento

COLLECTION_NAME = "maratona_eventos"


def criar_indice(eventos: list[Evento], persist_dir: str = "./chroma_db") -> chromadb.Collection:
    """Cria/recria o índice vetorial com todos os eventos."""
    client = chromadb.PersistentClient(path=persist_dir)

    # Remove coleção anterior se existir
    try:
        client.delete_collection(COLLECTION_NAME)
    except (ValueError, chromadb.errors.NotFoundError):
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Prepara dados para inserção em batch
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for evento in eventos:
        ids.append(evento.id)
        documents.append(evento.texto_para_busca())
        metadatas.append({
            "data": evento.data,
            "dia_semana": evento.dia_semana,
            "bairro": evento.bairro.lower(),
            "nome_local": evento.nome_local,
            "classificacao": evento.classificacao.lower(),
            "categoria": evento.categoria,
            "genero": evento.genero,
            "publico": evento.publico,
            "titulo": evento.titulo,
            "horario_inicio_min": evento.horario_inicio_minutos or -1,
            "horario_fim_min": evento.horario_fim_minutos or -1,
            "secao": evento.secao,
        })

    # Insere em batches de 500
    batch_size = 500
    for i in range(0, len(ids), batch_size):
        collection.add(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )

    return collection


def carregar_indice(persist_dir: str = "./chroma_db") -> chromadb.Collection:
    """Carrega o índice existente."""
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_collection(COLLECTION_NAME)
