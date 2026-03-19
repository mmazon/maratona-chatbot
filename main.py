"""Maratona Cultural Chatbot — Ponto de entrada.

Uso:
    python main.py                # Modo interativo (chatbot)
    python main.py --indexar      # Apenas indexar o PDF
    python main.py --stats        # Estatísticas da extração
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from src.extraction.pdf_extractor import extrair_texto_pdf
from src.extraction.parser import parsear_programacao
from src.models.evento import Evento
from src.search.indexador import criar_indice, carregar_indice
from src.search.buscador import Buscador
from src.chatbot.assistente import Assistente

load_dotenv()

PDF_PATH = "maratona.pdf"
CHROMA_DIR = "./chroma_db"
EVENTOS_JSON = "./eventos_extraidos.json"


def extrair_e_indexar() -> tuple[list[Evento], Buscador]:
    """Extrai eventos do PDF e cria índice vetorial."""
    print("📄 Extraindo texto do PDF...")
    texto = extrair_texto_pdf(PDF_PATH)

    print("🔍 Parseando programação...")
    eventos = parsear_programacao(texto)
    print(f"   ✅ {len(eventos)} eventos extraídos")

    # Salva eventos como JSON para inspeção
    eventos_dict = [e.model_dump() for e in eventos]
    with open(EVENTOS_JSON, "w", encoding="utf-8") as f:
        json.dump(eventos_dict, f, ensure_ascii=False, indent=2)
    print(f"   💾 Eventos salvos em {EVENTOS_JSON}")

    print("📊 Criando índice vetorial...")
    collection = criar_indice(eventos, CHROMA_DIR)
    print(f"   ✅ Índice criado com {collection.count()} documentos")

    buscador = Buscador(collection, eventos)
    return eventos, buscador


def carregar_sistema() -> tuple[list[Evento], Buscador]:
    """Carrega sistema a partir de dados já indexados."""
    if not Path(EVENTOS_JSON).exists():
        return extrair_e_indexar()

    print("📂 Carregando eventos salvos...")
    with open(EVENTOS_JSON, "r", encoding="utf-8") as f:
        dados = json.load(f)
    eventos = [Evento(**d) for d in dados]
    print(f"   ✅ {len(eventos)} eventos carregados")

    try:
        collection = carregar_indice(CHROMA_DIR)
        print(f"   ✅ Índice vetorial carregado ({collection.count()} docs)")
    except Exception:
        print("   ⚠️ Índice não encontrado, recriando...")
        collection = criar_indice(eventos, CHROMA_DIR)

    buscador = Buscador(collection, eventos)
    return eventos, buscador


def mostrar_estatisticas(eventos: list[Evento]):
    """Mostra estatísticas da extração."""
    print(f"\n📊 ESTATÍSTICAS DA EXTRAÇÃO")
    print(f"{'='*50}")
    print(f"Total de eventos: {len(eventos)}")

    print(f"\n📅 Por dia:")
    for data, qtd in sorted(Counter(e.data for e in eventos).items()):
        dia = next((e.dia_semana for e in eventos if e.data == data), "")
        print(f"   {data} ({dia}): {qtd} eventos")

    print(f"\n🏷️ Por categoria:")
    for cat, qtd in Counter(e.categoria for e in eventos).most_common():
        print(f"   {cat}: {qtd}")

    print(f"\n📍 Por bairro (top 15):")
    for bairro, qtd in Counter(e.bairro for e in eventos).most_common(15):
        print(f"   {bairro or '(não identificado)'}: {qtd}")

    print(f"\n🎵 Por gênero:")
    generos = Counter(e.genero for e in eventos if e.genero)
    for gen, qtd in generos.most_common():
        print(f"   {gen}: {qtd}")

    print(f"\n👥 Por público:")
    for pub, qtd in Counter(e.publico for e in eventos).most_common():
        print(f"   {pub}: {qtd}")


def modo_interativo(buscador: Buscador):
    """Loop interativo do chatbot."""
    assistente = Assistente(buscador)

    print(f"\n{'='*60}")
    print("🎭 CHATBOT DA MARATONA CULTURAL DE FLORIANÓPOLIS 2025")
    print(f"{'='*60}")
    print("Pergunte sobre a programação! Exemplos:")
    print('  • "Quero shows de hip hop no Centro"')
    print('  • "O que tem pra crianças à tarde?"')
    print('  • "Me sugere um roteiro com música e depois um bar"')
    print('  • "Teatro depois das 20h no Centro"')
    print('  • "Exposições no sábado"')
    print()
    print('Digite "sair" para encerrar.')
    print(f"{'='*60}\n")

    while True:
        try:
            pergunta = input("🗣️ Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Até mais! Aproveite a Maratona Cultural!")
            break

        if not pergunta:
            continue

        if pergunta.lower() in ("sair", "exit", "quit", "q"):
            print("👋 Até mais! Aproveite a Maratona Cultural!")
            break

        print()
        resposta = assistente.responder(pergunta)
        print(f"🤖 Assistente:\n{resposta}\n")


def main():
    parser = argparse.ArgumentParser(description="Chatbot Maratona Cultural")
    parser.add_argument("--indexar", action="store_true", help="Reindexar PDF")
    parser.add_argument("--stats", action="store_true", help="Mostrar estatísticas")
    args = parser.parse_args()

    if args.indexar:
        eventos, buscador = extrair_e_indexar()
        mostrar_estatisticas(eventos)
        return

    if args.stats:
        eventos, _ = carregar_sistema()
        mostrar_estatisticas(eventos)
        return

    eventos, buscador = carregar_sistema()
    modo_interativo(buscador)


if __name__ == "__main__":
    main()
