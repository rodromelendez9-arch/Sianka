"""Cifrado de datos personales a nivel de aplicacion.

Supabase ya cifra el disco, pero eso no protege contra alguien que obtenga
la service_role key, un respaldo o acceso al SQL Editor: veria telefonos,
nombres y conversaciones completas en texto plano. Por eso los campos con
datos personales (telefono, nombre del cliente, transcripcion) se guardan
cifrados con AES-256-GCM usando una clave que solo tiene el servidor
(DATA_ENCRYPTION_KEY) y que nunca se guarda en la base.

Como un valor cifrado no se puede buscar, el telefono ademas se guarda como
"huella" (HMAC-SHA256 con otra clave derivada): permite encontrar todas las
llamadas de un numero para atender derechos ARCO sin poder revertirla al
numero original.

IMPORTANTE: si se pierde DATA_ENCRYPTION_KEY, los datos cifrados son
irrecuperables. Respaldala fuera del servidor (gestor de secretos).
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIJO = "enc:v1:"
_NONCE_BYTES = 12

_claves: Optional[tuple[bytes, bytes]] = None


def generar_clave() -> str:
    """Clave nueva para DATA_ENCRYPTION_KEY (32 bytes en base64)."""
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def _cargar_claves() -> tuple[bytes, bytes]:
    global _claves
    if _claves is None:
        valor = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
        if not valor:
            raise RuntimeError(
                "DATA_ENCRYPTION_KEY no esta configurada. Genera una con "
                "`python admin.py generar-clave`, guardala en .env y respaldala."
            )
        try:
            maestra = base64.urlsafe_b64decode(valor)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("DATA_ENCRYPTION_KEY no es base64 valido") from exc
        if len(maestra) != 32:
            raise RuntimeError("DATA_ENCRYPTION_KEY debe decodificar a 32 bytes")

        # Dos subclaves independientes: una para cifrar, otra para la huella
        # del telefono. Asi la huella no revela nada sobre la clave de cifrado.
        clave_cifrado = hmac.new(maestra, b"sianka-cifrado-v1", hashlib.sha256).digest()
        clave_indice = hmac.new(maestra, b"sianka-indice-telefono-v1", hashlib.sha256).digest()
        _claves = (clave_cifrado, clave_indice)
    return _claves


def verificar_configuracion() -> None:
    """Se llama al arrancar: sin clave el servidor no debe aceptar llamadas
    (guardaria datos personales en claro o fallaria a media llamada)."""
    _cargar_claves()


def cifrar(texto: Optional[str]) -> Optional[str]:
    if texto is None or texto == "":
        return texto
    clave, _ = _cargar_claves()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    cifrado = AESGCM(clave).encrypt(nonce, texto.encode("utf-8"), None)
    return _PREFIJO + base64.urlsafe_b64encode(nonce + cifrado).decode("ascii")


def descifrar(valor: Optional[str]) -> Optional[str]:
    """Valores sin prefijo se devuelven tal cual: son filas anteriores al
    cifrado (se migran con `python admin.py cifrar-existentes`)."""
    if not valor or not valor.startswith(_PREFIJO):
        return valor
    clave, _ = _cargar_claves()
    crudo = base64.urlsafe_b64decode(valor[len(_PREFIJO):])
    nonce, cifrado = crudo[:_NONCE_BYTES], crudo[_NONCE_BYTES:]
    return AESGCM(clave).decrypt(nonce, cifrado, None).decode("utf-8")


def esta_cifrado(valor: Optional[str]) -> bool:
    return bool(valor) and valor.startswith(_PREFIJO)


def normalizar_telefono(telefono: Optional[str]) -> Optional[str]:
    """"+52 999 123 4567" -> "+529991234567". None si no es un numero
    (Twilio manda "Anonymous" o similar cuando el numero es privado)."""
    if not telefono:
        return None
    limpio = re.sub(r"[^\d+]", "", telefono)
    return limpio if re.fullmatch(r"\+?\d{7,15}", limpio) else None


def huella_telefono(telefono: Optional[str]) -> Optional[str]:
    normalizado = normalizar_telefono(telefono)
    if not normalizado:
        return None
    _, clave_indice = _cargar_claves()
    return hmac.new(clave_indice, normalizado.encode("utf-8"), hashlib.sha256).hexdigest()


def enmascarar_telefono(telefono: Optional[str]) -> str:
    """Para mostrar en pantalla: "•••• 4567". El panel no necesita el numero
    completo para operar (minimizacion de datos)."""
    normalizado = normalizar_telefono(telefono)
    if not normalizado:
        return "Numero privado"
    return f"•••• {normalizado[-4:]}"
