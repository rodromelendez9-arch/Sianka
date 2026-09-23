"""Datos publicos del sitio: URL base (para canonical, sitemap y el aviso que
dice el agente) y la identidad legal de Sianka como responsable/encargado
en los avisos de privacidad. Vienen de .env para no dejar datos legales
fijos en el codigo."""
import os
from urllib.parse import urlparse

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://sianka.mx").rstrip("/")

SIANKA_RAZON_SOCIAL = os.getenv("SIANKA_RAZON_SOCIAL", "").strip()
SIANKA_DOMICILIO = os.getenv("SIANKA_DOMICILIO", "").strip()
SIANKA_EMAIL_PRIVACIDAD = os.getenv("SIANKA_EMAIL_PRIVACIDAD", "").strip()

# Fecha de la version vigente de los textos legales. Actualizala cada vez
# que cambie el contenido de /privacidad o /terminos.
FECHA_TEXTOS_LEGALES = "23 de septiembre de 2026"

# Cuanto se conservan las transcripciones antes de borrarse solas.
RETENCION_TRANSCRIPCIONES_DIAS = int(os.getenv("RETENCION_TRANSCRIPCIONES_DIAS", "90"))


def datos_legales_completos() -> bool:
    return bool(SIANKA_RAZON_SOCIAL and SIANKA_DOMICILIO and SIANKA_EMAIL_PRIVACIDAD)


def url(ruta: str) -> str:
    return f"{PUBLIC_BASE_URL}{ruta}"


def host() -> str:
    return urlparse(PUBLIC_BASE_URL).netloc or PUBLIC_BASE_URL


def host_hablado() -> str:
    """Como lo pronuncia el agente por telefono: "sianka.mx" ->
    "sianka punto m x"."""
    partes = host().split(".")
    if len(partes) > 1 and len(partes[-1]) <= 3:
        partes[-1] = " ".join(partes[-1])
    return " punto ".join(partes)
