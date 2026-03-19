"""Assistente da Maratona Cultural — gera respostas usando OpenAI."""

from __future__ import annotations

import os
from openai import OpenAI, AuthenticationError
from src.models.evento import Evento
from src.search.buscador import Buscador
from src.search.query_parser import parsear_query, QueryParseada

SYSTEM_PROMPT = """Você é o assistente oficial da Maratona Cultural de Florianópolis 2026.

Seu papel:
- Ajudar o público a encontrar eventos na programação
- Responder SEMPRE em português brasileiro (PT-BR)
- Ser simpático, objetivo e útil
- NUNCA inventar ou alterar dados — use APENAS os campos fornecidos no contexto
- Se não encontrar resultados, diga isso claramente

=== ATRAÇÕES PRINCIPAIS (DESTAQUES) ===
Quando o usuário perguntar sobre "atração principal", "show principal", "destaque",
"headliner" ou "grande show" de um dia específico, responda com estas informações:

- SÁBADO (21/03): JOELMA — Arena Floripa (palco principal), Centro
- DOMINGO (22/03): MARISA MONTE — Arena Floripa (palco principal), Centro
- SEGUNDA-FEIRA (23/03, feriado em Florianópolis): ADRIANA CALCANHOTTO É PARTIMPIM: O QUARTO NO PALCO — show infantil na Maratoninha, Centro (Parque da Luz). Não precisa de ingresso.

Sobre ingressos dos shows principais na Arena Floripa (Joelma e Marisa Monte):
os ingressos são retirados na plataforma pensenoevento.com.br

Se o usuário perguntar de forma genérica ("quais são as atrações principais?"),
liste os três destaques acima.
================================================

=== REGRA SOBRE INGRESSOS (MUITO IMPORTANTE) ===
- NUNCA sugira, afirme ou invente informações sobre ingressos, preços ou formas de retirada.
- Cada evento tem sua própria forma de distribuição de ingressos.
- Apenas repita as informações de ingresso que estiverem EXPLICITAMENTE no campo "Info" do contexto da busca.
- Se não houver informação de ingresso no contexto, NÃO mencione ingressos.
- SEMPRE que mencionar qualquer informação sobre ingressos (incluindo os shows principais), adicione "sujeito a disponibilidade".
- EXCEÇÃO: para os shows principais (Joelma e Marisa Monte na Arena Floripa), informe que os ingressos são pela plataforma pensenoevento.com.br. Para Adriana Calcanhotto na Maratoninha, informe que não precisa de ingresso.
================================================

Regras CRÍTICAS:
1. Use EXATAMENTE os dados dos campos do contexto. Não combine, modifique ou invente informações.
2. O campo "Título" é o nome do evento. O campo "Local" é o nome do local. NÃO misture os dois.
3. Ao listar um evento, copie os valores exatos dos campos: Título, Local, Bairro, Horário, Classificação.
4. Se a busca retornar poucos resultados, sugira alternativas próximas
5. Para roteiros, organize cronologicamente e considere deslocamento
6. Avise sobre classificação etária quando relevante
7. Seja conciso mas completo

Formato de resposta:
- Use emojis com moderação (🎭🎵📍🕐)
- Liste eventos de forma clara e organizada
- Agrupe por horário quando fizer sentido"""


class Assistente:
    """Chatbot da Maratona Cultural."""

    def __init__(self, buscador: Buscador):
        self.buscador = buscador
        # Tenta pegar a key do Streamlit secrets, senão do env
        api_key = os.environ.get("OPENAI_API_KEY", "")
        try:
            import streamlit as st
            api_key = st.secrets.get("OPENAI_API_KEY", api_key)
        except Exception:
            pass
        self.client = OpenAI(api_key=api_key)
        self.historico: list[dict] = []

    def responder(self, pergunta: str) -> str:
        """Processa pergunta do usuário e retorna resposta."""
        # 1. Parseia a query
        query = parsear_query(pergunta)

        # 2. Busca eventos
        if query.intencao == "roteiro":
            resultados = self.buscador.buscar_por_roteiro(
                query.texto_busca, query.filtros
            )
        else:
            resultados = self.buscador.buscar(
                query.texto_busca, query.filtros
            )

        # 3. Monta contexto
        contexto = self._montar_contexto(query, resultados)

        # 4. Gera resposta com OpenAI
        resposta = self._chamar_llm(pergunta, contexto, query)

        # 5. Atualiza histórico
        self.historico.append({"role": "user", "content": pergunta})
        self.historico.append({"role": "assistant", "content": resposta})

        # Mantém histórico curto
        if len(self.historico) > 10:
            self.historico = self.historico[-10:]

        return resposta

    def _montar_contexto(
        self,
        query: QueryParseada,
        resultados: list[tuple[Evento, float]],
    ) -> str:
        """Monta o contexto com os eventos encontrados."""
        partes = [
            f"Pergunta do usuário: {query.texto_original}",
            f"Filtros detectados: {query.descricao_filtros()}",
            f"Intenção: {query.intencao}",
            f"Total de resultados: {len(resultados)}",
            "",
            "=== EVENTOS ENCONTRADOS ===",
        ]

        if not resultados:
            partes.append("Nenhum evento encontrado com esses critérios.")
            partes.append("")
            partes.append(
                "Sugira ao usuário reformular a busca ou remover filtros."
            )
        else:
            for i, (evento, score) in enumerate(resultados, 1):
                partes.append(f"\n--- Evento {i} (relevância: {score:.2f}) ---")
                partes.append(f"Título: {evento.titulo}")
                partes.append(f"Data: {evento.data} ({evento.dia_semana})")
                partes.append(f"Horário: {evento.texto_horario_original}")
                partes.append(f"Local: {evento.nome_local}")
                partes.append(f"Endereço: {evento.endereco}")
                partes.append(f"Bairro: {evento.bairro}")
                partes.append(f"Classificação: {evento.classificacao}")
                if evento.categoria:
                    partes.append(f"Categoria: {evento.categoria}")
                if evento.genero:
                    partes.append(f"Gênero: {evento.genero}")
                if evento.descricao:
                    partes.append(f"Descrição: {evento.descricao}")
                if evento.origem:
                    partes.append(f"Origem: {evento.origem}")
                if evento.informacoes_adicionais:
                    partes.append(f"Info: {evento.informacoes_adicionais}")

        # Se a busca é ampla, instrui o LLM a sugerir filtros
        if query.busca_ampla and resultados:
            partes.append("")
            partes.append(
                "INSTRUÇÃO: A busca do usuário é ampla (poucos filtros). "
                "Após listar os eventos mais relevantes, sugira ao usuário "
                "refinar a busca. Por exemplo: filtrar por dia (sexta, sábado, "
                "domingo ou segunda), por bairro (Centro, Lagoa, Campeche...), "
                "ou por horário (manhã, tarde, noite)."
            )

        return "\n".join(partes)

    def _chamar_llm(self, pergunta: str, contexto: str, query: QueryParseada) -> str:
        """Chama OpenAI para gerar a resposta."""
        mensagens = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensagens.extend(self.historico)
        mensagens.append({
            "role": "user",
            "content": f"{pergunta}\n\n[CONTEXTO DA BUSCA]\n{contexto}",
        })

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1500,
                messages=mensagens,
            )
            return response.choices[0].message.content
        except AuthenticationError:
            return self._resposta_sem_llm(pergunta, contexto, query)
        except Exception as e:
            return f"Desculpe, ocorreu um erro ao gerar a resposta: {e}"

    def _resposta_sem_llm(
        self, pergunta: str, contexto: str, query: QueryParseada
    ) -> str:
        """Resposta fallback sem LLM (quando API key não disponível)."""
        linhas = contexto.split("\n")
        eventos_texto = []
        evento_atual: list[str] = []
        for linha in linhas:
            if linha.startswith("--- Evento"):
                if evento_atual:
                    eventos_texto.append("\n".join(evento_atual))
                evento_atual = []
            elif linha.startswith("Título:"):
                evento_atual.append(f"🎭 {linha[8:]}")
            elif linha.startswith("Local:"):
                evento_atual.append(f"📍 {linha[7:]}")
            elif linha.startswith("Horário:"):
                evento_atual.append(f"🕐 {linha[9:]}")
            elif linha.startswith("Data:"):
                evento_atual.append(f"📅 {linha[6:]}")
            elif linha.startswith("Bairro:"):
                evento_atual.append(f"📍 Bairro: {linha[8:]}")
            elif linha.startswith("Classificação:"):
                evento_atual.append(f"🎫 {linha}")
            elif linha.startswith("Info:"):
                evento_atual.append(f"💡 {linha[6:]}")
        if evento_atual:
            eventos_texto.append("\n".join(evento_atual))

        if not eventos_texto:
            return (
                "Não encontrei eventos com esses critérios. "
                "Tente reformular sua busca ou remover alguns filtros."
            )

        resultado = f"Encontrei {len(eventos_texto)} evento(s) para você:\n\n"
        resultado += "\n\n".join(eventos_texto)
        if query.busca_ampla:
            resultado += (
                "\n\n💡 Dica: refine sua busca! Tente filtrar por dia "
                "(sexta, sábado, domingo), bairro (Centro, Lagoa, Campeche) "
                "ou horário (manhã, tarde, noite)."
            )

        resultado += (
            "\n\n⚠️ Resposta gerada sem LLM (configure OPENAI_API_KEY "
            "no .env para respostas mais naturais)"
        )
        return resultado
