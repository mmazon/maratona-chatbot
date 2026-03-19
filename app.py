"""Maratona Cultural Chatbot — Interface Streamlit."""

import streamlit as st
from dotenv import load_dotenv

from src.extraction.pdf_extractor import extrair_texto_pdf
from src.extraction.parser import parsear_programacao
from src.models.evento import Evento
from src.search.indexador import criar_indice, carregar_indice
from src.search.buscador import Buscador
from src.chatbot.assistente import Assistente

import json
from pathlib import Path

load_dotenv()

PDF_PATH = "maratona.pdf"
CHROMA_DIR = "./chroma_db"
EVENTOS_JSON = "./eventos_extraidos.json"


@st.cache_resource
def carregar_sistema():
    """Carrega ou cria o índice de eventos (cached)."""
    if Path(EVENTOS_JSON).exists():
        with open(EVENTOS_JSON, "r", encoding="utf-8") as f:
            dados = json.load(f)
        eventos = [Evento(**d) for d in dados]
        try:
            collection = carregar_indice(CHROMA_DIR)
        except Exception:
            collection = criar_indice(eventos, CHROMA_DIR)
    else:
        texto = extrair_texto_pdf(PDF_PATH)
        eventos = parsear_programacao(texto)
        with open(EVENTOS_JSON, "w", encoding="utf-8") as f:
            json.dump([e.model_dump() for e in eventos], f, ensure_ascii=False, indent=2)
        collection = criar_indice(eventos, CHROMA_DIR)

    buscador = Buscador(collection, eventos)
    return buscador


def init_assistente(buscador: Buscador) -> Assistente:
    """Cria ou recupera o assistente da sessão."""
    if "assistente" not in st.session_state:
        st.session_state.assistente = Assistente(buscador)
    return st.session_state.assistente


# ── Page Config ──
st.set_page_config(
    page_title="Maratona Cultural Floripa 2025",
    page_icon="🎭",
    layout="centered",
)

# ── CSS com identidade visual da Maratona ──
st.markdown("""
<style>
    /* Cores da identidade visual */
    :root {
        --roxo: #7B2D8E;
        --roxo-escuro: #5a1d6b;
        --vermelho: #D4272E;
        --amarelo: #E8A32E;
        --laranja: #D4702E;
        --branco: #FAFAFA;
    }

    /* Header estilizado */
    .maratona-header {
        background: linear-gradient(135deg, #7B2D8E 0%, #5a1d6b 100%);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
        text-align: center;
        border-bottom: 4px solid #D4272E;
    }
    .maratona-header h1 {
        color: #E8A32E;
        font-size: 1.8rem;
        margin: 0;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .maratona-header .subtitle {
        color: #FAFAFA;
        font-size: 1rem;
        margin-top: 0.3rem;
        font-weight: 300;
    }
    .maratona-header .dates {
        color: #D4272E;
        font-weight: 700;
        font-size: 1.1rem;
        background: #FAFAFA;
        display: inline-block;
        padding: 0.2rem 0.8rem;
        border-radius: 4px;
        margin-top: 0.5rem;
    }

    /* Chat messages */
    .stChatMessage [data-testid="stMarkdownContainer"] p {
        font-size: 0.95rem;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #7B2D8E 0%, #5a1d6b 100%);
    }
    section[data-testid="stSidebar"] h3 {
        color: #E8A32E !important;
    }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] li {
        color: #FAFAFA !important;
    }

    /* Botões de sugestão */
    .stButton > button {
        border: 1px solid #7B2D8E;
        border-radius: 8px;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        border-color: #D4272E;
        background-color: rgba(212, 39, 46, 0.1);
    }

    /* Destaque cards */
    .destaque-card {
        background: linear-gradient(135deg, #7B2D8E22, #D4272E11);
        border-left: 4px solid #D4272E;
        padding: 0.8rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 0.3rem 0;
    }
    .destaque-card .dia {
        color: #E8A32E;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .destaque-card .artista {
        color: #FAFAFA;
        font-weight: 600;
        font-size: 1rem;
    }
    .destaque-card .local {
        color: #aaa;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ──
st.markdown("""
<div class="maratona-header">
    <h1>🎭 Maratona Cultural</h1>
    <div class="subtitle">Florianópolis — Mais Arte · Mais Cidade · Mais Vida</div>
    <div class="dates">20 — 23 MAR / 2026</div>
</div>
""", unsafe_allow_html=True)

# ── Carregar sistema ──
buscador = carregar_sistema()
assistente = init_assistente(buscador)

# ── Histórico do chat ──
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sugestões rápidas (só aparece se chat vazio) ──
if not st.session_state.messages:
    st.markdown("#### 💡 Pergunte sobre a programação")
    cols = st.columns(2)
    sugestoes = [
        ("⭐ Atrações principais", "Quais são as atrações principais?"),
        ("👶 Infantil na segunda", "O que tem pra crianças na segunda?"),
        ("🎵 Samba no sábado", "Shows de samba no sábado"),
        ("🖼️ Exposições no Centro", "Exposições no Centro"),
        ("🗺️ Roteiro de domingo", "Roteiro de shows para domingo à tarde"),
        ("🏟️ Arena Floripa", "O que tem na Arena Floripa?"),
    ]
    for i, (label, query) in enumerate(sugestoes):
        col = cols[i % 2]
        if col.button(label, key=f"sug_{i}", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": query})
            with st.spinner("Buscando..."):
                resposta = assistente.responder(query)
            st.session_state.messages.append({"role": "assistant", "content": resposta})
            st.rerun()

# ── Renderiza mensagens ──
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🗣️" if msg["role"] == "user" else "🎭"):
        st.markdown(msg["content"])

# ── Input do chat ──
if prompt := st.chat_input("Pergunte sobre a programação..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="🗣️"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="🎭"):
        with st.spinner("Buscando na programação..."):
            resposta = assistente.responder(prompt)
        st.markdown(resposta)

    st.session_state.messages.append({"role": "assistant", "content": resposta})

# ── Sidebar ──
with st.sidebar:
    # Logo/capa
    if Path("assets/capa.png").exists():
        st.image("assets/capa.png", use_container_width=True)
    st.markdown("---")

    st.markdown("### ⭐ Destaques")
    st.markdown("""
<div class="destaque-card">
    <div class="dia">SÁB 21/03</div>
    <div class="artista">🎤 Joelma</div>
    <div class="local">Arena Floripa (palco principal)</div>
</div>
<div class="destaque-card">
    <div class="dia">DOM 22/03</div>
    <div class="artista">🎤 Marisa Monte</div>
    <div class="local">Arena Floripa (palco principal)</div>
</div>
<div class="destaque-card">
    <div class="dia">SEG 23/03 (feriado)</div>
    <div class="artista">🎤 Adriana Calcanhotto É Partimpim</div>
    <div class="local">Maratoninha — Parque da Luz</div>
</div>
""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 📅 Programação")
    st.markdown("""
    - **Sex 20/03** — Abertura
    - **Sáb 21/03** — Joelma
    - **Dom 22/03** — Marisa Monte
    - **Seg 23/03** — Partimpim (infantil)
    """)

    st.markdown("---")
    st.markdown("### 🗺️ Bairros")
    st.markdown(
        "Centro · Agronômica · Lagoa · Campeche · "
        "Trindade · Coqueiros · Santo Antônio"
    )

    st.markdown("---")
    st.markdown("### 🏷️ Categorias")
    st.markdown(
        "Shows · Teatro · Exposições · Cinema · "
        "Oficinas · Feiras · Circo · Infantil"
    )

    st.markdown("---")
    if st.button("🗑️ Limpar conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop("assistente", None)
        st.rerun()

    st.markdown("---")
    st.caption("Feito com ❤️ para a Maratona Cultural de Florianópolis")
