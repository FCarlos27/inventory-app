PREFIJOS_PELIGROSOS = ("=", "+", "-", "@", "\t", "\r")


def celda_segura(valor: str | None) -> str:
    """Evita que Excel interprete un valor como fórmula."""
    texto = valor or ""
    if texto.startswith(PREFIJOS_PELIGROSOS):
        return "'" + texto
    return texto
