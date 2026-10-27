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

# Contacto comercial de la pagina de venta (/). Todos son opcionales: si
# falta alguno, su boton simplemente no se muestra.
CONTACTO_WHATSAPP = "".join(c for c in os.getenv("SIANKA_WHATSAPP", "") if c.isdigit())
CONTACTO_EMAIL = os.getenv("SIANKA_EMAIL_CONTACTO", "").strip()
# Numero de demostracion al que un prospecto puede llamar para probar el agente
TELEFONO_DEMO = os.getenv("SIANKA_TELEFONO_DEMO", "").strip()


def whatsapp_url(mensaje: str = "Hola, quiero ver una demo de Sianka para mi restaurante") -> str:
    from urllib.parse import quote

    return f"https://wa.me/{CONTACTO_WHATSAPP}?text={quote(mensaje)}" if CONTACTO_WHATSAPP else ""


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


def url_hablada(direccion: str) -> str:
    """Como pronuncia el agente una URL por telefono:
    "https://tacos.mx/privacidad" -> "tacos punto m x diagonal privacidad"."""
    partes_url = urlparse(direccion if "//" in direccion else f"//{direccion}")
    dominio = (partes_url.netloc or "").removeprefix("www.")
    partes = dominio.split(".")
    if len(partes) > 1 and len(partes[-1]) <= 3:
        partes[-1] = " ".join(partes[-1])
    hablado = " punto ".join(partes)
    ruta = partes_url.path.strip("/")
    if ruta:
        hablado += " diagonal " + " diagonal ".join(ruta.replace("-", " ").split("/"))
    return hablado
