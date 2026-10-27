"""Suite de pruebas. Ejecutar desde la raiz del proyecto:

    python -m unittest discover -s tests -t .

Este archivo corre ANTES de importar cualquier modulo de la app: fija
variables de entorno falsas (main.py llama load_dotenv(), que no sobrescribe
las que ya existen) para que ninguna prueba pueda usar las claves reales del
.env ni hablar con Supabase, Twilio, Deepgram o Anthropic.
"""
import base64
import os

os.environ.update(
    {
        "SESSION_HTTPS_ONLY": "false",
        "LOG_LEVEL": "CRITICAL",
        "SESSION_SECRET_KEY": "clave-de-sesion-de-pruebas",
        "DATA_ENCRYPTION_KEY": base64.urlsafe_b64encode(b"k" * 32).decode(),
        "TWILIO_AUTH_TOKEN": "token-de-pruebas",
        "SUPABASE_URL": "http://supabase.invalid",
        "SUPABASE_KEY": "llave-de-pruebas",
        "ANTHROPIC_API_KEY": "llave-de-pruebas",
        "DEEPGRAM_API_KEY": "llave-de-pruebas",
        "PUBLIC_BASE_URL": "https://sianka.mx",
        "SIANKA_RAZON_SOCIAL": "",
        "SIANKA_DOMICILIO": "",
        "SIANKA_EMAIL_PRIVACIDAD": "",
    }
)

# La base falsa se instala aqui, una sola vez, antes que cualquier prueba:
# asi es imposible que una prueba escriba en la base real por accidente.
from tests import fakes  # noqa: E402

fakes.instalar()
