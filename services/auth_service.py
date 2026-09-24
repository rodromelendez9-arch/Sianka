import hashlib
import secrets
from typing import Optional

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

from database import supabase_client

# La sesion guarda a que restaurante pertenece el usuario: TODO el dashboard
# (paginas, /api/* y el WebSocket) se filtra por este id, asi que un
# restaurante nunca ve ni modifica datos de otro.
SESSION_USUARIO = "usuario_id"
SESSION_RESTAURANTE = "restaurante_id"

# Parametros de scrypt (hashlib, sin dependencias extra). n=2**14 es el
# minimo recomendado para logins interactivos: ~50ms por intento.
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hashear_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def _verificar_hash(password: str, almacenado: str) -> bool:
    try:
        algoritmo, n, r, p, salt_hex, digest_hex = almacenado.split("$")
        if algoritmo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(digest.hex(), digest_hex)


# Hash de relleno: si el email no existe se verifica contra esto igualmente,
# para que la respuesta tarde lo mismo y no revele que correos estan dados
# de alta (enumeracion de usuarios por tiempo de respuesta).
_HASH_RELLENO = hashear_password(secrets.token_hex(16))


def autenticar(email: str, password: str) -> Optional[dict]:
    """Devuelve el usuario si email y contrasena son correctos y su
    restaurante sigue activo; si no, None."""
    usuario = supabase_client.get_usuario_por_email(email) if email.strip() else None
    if not usuario:
        _verificar_hash(password, _HASH_RELLENO)
        return None

    if not _verificar_hash(password, usuario["password_hash"]):
        return None

    restaurante = supabase_client.get_restaurante(usuario["restaurante_id"])
    if not restaurante or not restaurante.get("activo"):
        return None

    return usuario


def iniciar_sesion(request: Request, usuario: dict) -> None:
    request.session.clear()
    request.session[SESSION_USUARIO] = str(usuario["id"])
    request.session[SESSION_RESTAURANTE] = str(usuario["restaurante_id"])


def cerrar_sesion(request: Request) -> None:
    request.session.clear()


def restaurante_de_sesion(conn: HTTPConnection) -> Optional[str]:
    """`HTTPConnection` es la clase base compartida por `Request` y
    `WebSocket`, asi que esto sirve para ambos tipos de conexion."""
    return conn.session.get(SESSION_RESTAURANTE)


def require_login(request: Request) -> str:
    """Dependencia de FastAPI para RUTAS HTTP del dashboard y de /api/*.
    Devuelve el `restaurante_id` del usuario con sesion iniciada:

        async def mi_ruta(restaurante_id: str = Depends(require_login)): ...

    NO se aplica al webhook de Twilio, a /health, ni a /robots.txt -- esos
    los llama Twilio o un monitor externo, no un empleado con sesion
    iniciada. Para el WebSocket /ws/dashboard no se puede usar esta misma
    dependencia (un `Depends` con `Request` no se resuelve en conexiones
    WebSocket); ese caso se valida en el handler con `restaurante_de_sesion()`."""
    restaurante_id = restaurante_de_sesion(request)
    if not restaurante_id:
        raise HTTPException(status_code=401, detail="Inicia sesion para continuar")
    return restaurante_id
