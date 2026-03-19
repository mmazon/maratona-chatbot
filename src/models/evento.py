"""Modelo de dados para eventos da Maratona Cultural."""

from __future__ import annotations

import uuid
from pydantic import BaseModel, Field


class Horario(BaseModel):
    """Representa um horário ou intervalo de horário."""

    inicio: str  # "19:00"
    fim: str | None = None  # "21:00" ou None se horário pontual
    texto_original: str  # "19h—21h" ou "19h"


class Evento(BaseModel):
    """Modelo principal de um evento da Maratona Cultural."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])

    # Quando
    data: str  # "20/03"
    dia_semana: str  # "SEXTA-FEIRA"
    horarios: list[Horario]
    texto_horario_original: str  # texto bruto dos horários

    # Onde
    nome_local: str  # "TEATRO ÁLVARO DE CARVALHO - TAC"
    endereco: str  # "Rua Mal. Guilherme, 26"
    bairro: str  # "Centro"
    classificacao: str  # "16 anos", "livre", "18 anos"

    # O quê
    titulo: str  # "MEU CORPO ESTÁ AQUI"
    descricao: str = ""  # detalhes adicionais
    categoria: str = ""  # "show", "teatro", "exposição", etc.
    genero: str = ""  # "MPB", "hip hop", "jazz", etc.
    publico: str = ""  # "infantil", "adulto", "família"

    # Extras
    origem: str = ""  # "Florianópolis/SC", "Rio de Janeiro/RJ"
    informacoes_adicionais: str = ""  # ingressos, vagas, etc.
    tags: list[str] = Field(default_factory=list)
    secao: str = ""  # "PROGRAMAÇÃO OFF", "EVENTOS PARCEIROS", "MARATONINHA"

    # Rastreamento
    texto_bruto: str  # bloco de texto original completo
    arquivo_origem: str = "maratona.pdf"
    confianca_parse: float = 1.0  # 0.0 a 1.0

    @property
    def horario_inicio_minutos(self) -> int | None:
        """Retorna o primeiro horário como minutos desde meia-noite."""
        if not self.horarios:
            return None
        h, m = self.horarios[0].inicio.split(":")
        minutos = int(h) * 60 + int(m)
        # Horários como 0h30, 1h30 são madrugada (dia seguinte)
        if minutos < 5 * 60:
            minutos += 24 * 60
        return minutos

    @property
    def horario_fim_minutos(self) -> int | None:
        """Retorna o horário de fim como minutos desde meia-noite."""
        if not self.horarios:
            return None
        ultimo = self.horarios[-1]
        if ultimo.fim:
            h, m = ultimo.fim.split(":")
            minutos = int(h) * 60 + int(m)
            if minutos < 5 * 60:
                minutos += 24 * 60
            return minutos
        return None

    def texto_para_busca(self) -> str:
        """Gera texto otimizado para indexação vetorial."""
        partes = [
            f"{self.titulo}",
            f"Local: {self.nome_local}",
            f"Bairro: {self.bairro}",
            f"Data: {self.data} ({self.dia_semana})",
            f"Horário: {self.texto_horario_original}",
        ]
        if self.descricao:
            partes.append(self.descricao)
        if self.categoria:
            partes.append(f"Categoria: {self.categoria}")
        if self.genero:
            partes.append(f"Gênero: {self.genero}")
        if self.origem:
            partes.append(f"Origem: {self.origem}")
        if self.classificacao:
            partes.append(f"Classificação: {self.classificacao}")
        if self.informacoes_adicionais:
            partes.append(self.informacoes_adicionais)
        return " | ".join(partes)

    def resumo(self) -> str:
        """Gera um resumo legível do evento para respostas do chatbot."""
        linhas = [f"🎭 {self.titulo}"]
        linhas.append(f"📍 {self.nome_local} — {self.bairro}")
        linhas.append(f"📅 {self.data} ({self.dia_semana})")
        linhas.append(f"🕐 {self.texto_horario_original}")
        if self.classificacao:
            linhas.append(f"🎫 Classificação: {self.classificacao}")
        if self.descricao:
            linhas.append(f"ℹ️ {self.descricao}")
        if self.informacoes_adicionais:
            linhas.append(f"💡 {self.informacoes_adicionais}")
        return "\n".join(linhas)
