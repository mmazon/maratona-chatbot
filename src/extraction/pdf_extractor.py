"""Extrai texto bruto do PDF usando pdfplumber."""

from __future__ import annotations

import pdfplumber


def extrair_texto_pdf(caminho_pdf: str) -> str:
    """Extrai todo o texto do PDF, página por página."""
    paginas: list[str] = []
    with pdfplumber.open(caminho_pdf) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text()
            if texto:
                paginas.append(texto)
    return "\n".join(paginas)
