"""Costo estimado de cada llamada, para saber cuanto cuesta atender a cada
restaurante y poner precios con margen.

Las tarifas son en USD y se ajustan por variables de entorno cuando cambie
algun plan; los valores por defecto son aproximados. Es informacion interna:
se consulta con `python admin.py uso`, el panel del restaurante no la ve.
"""
import os
from typing import Any


def _tarifa(nombre: str, default: float) -> float:
    try:
        return float(os.getenv(nombre, default))
    except ValueError:
        return default


def tarifas() -> dict[str, float]:
    return {
        "telefonia_por_minuto": _tarifa("COSTO_TELEFONIA_MIN", 0.015),
        "transcripcion_por_minuto": _tarifa("COSTO_TRANSCRIPCION_MIN", 0.0077),
        "voz_por_mil_caracteres": _tarifa("COSTO_VOZ_1K_CARACTERES", 0.030),
        "modelo_entrada_por_millon": _tarifa("COSTO_MODELO_1M_ENTRADA", 1.00),
        "modelo_salida_por_millon": _tarifa("COSTO_MODELO_1M_SALIDA", 5.00),
    }


def estimar_costo_usd(uso: dict[str, Any]) -> float:
    """`uso`: duracion_segundos, tokens_entrada, tokens_salida, caracteres_voz.
    Telefonia y transcripcion se cobran por minuto iniciado."""
    t = tarifas()
    minutos = -(-int(uso.get("duracion_segundos") or 0) // 60)
    costo = (
        minutos * (t["telefonia_por_minuto"] + t["transcripcion_por_minuto"])
        + int(uso.get("caracteres_voz") or 0) / 1000 * t["voz_por_mil_caracteres"]
        + int(uso.get("tokens_entrada") or 0) / 1_000_000 * t["modelo_entrada_por_millon"]
        + int(uso.get("tokens_salida") or 0) / 1_000_000 * t["modelo_salida_por_millon"]
    )
    return round(costo, 4)
