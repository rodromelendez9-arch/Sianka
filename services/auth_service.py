import os
import secrets

from fastapi import HTTPException, Request
from starlette.requests import HTTPConnection

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")

SESSION_KEY = "autenticado"


def verificar_password(password: str) -> bool:
    """Compara con tiempo constante para no filtrar la contrasena por
    cuanto tarda la comparacion (timing attack)."""
    if not DASHBOARD_PASSWORD:
        return False
    return secrets.compare_digest(password, DASHBOARD_PASSWORD)


def iniciar_sesion(request: Request) -> None:
    request.session[SESSION_KEY] = True


def cerrar_sesion(request: Request) -> None:
    request.session.clear()


def esta_autenticado(conn: HTTPConnection) -> bool:
    """`HTTPConnection` es la clase base compartida por `Request` y
    `WebSocket`, asi que esto sirve para ambos tipos de conexion."""
    return bool(conn.session.get(SESSION_KEY))


def require_login(request: Request) -> None:
    """Dependencia de FastAPI para RUTAS HTTP: usar con
    `Depends(require_login)` en cualquier pagina del dashboard o endpoint
    de /api/*.

    NO se aplica al webhook de Twilio, a /health, ni a /robots.txt -- esos
    los llama Twilio o un monitor externo, no un empleado con sesion
    iniciada. Para el WebSocket /ws/dashboard no se puede usar esta misma
    dependencia (un `Depends` con `Request` no se resuelve en conexiones
    WebSocket); ese caso se valida directamente en el route handler con
    `esta_autenticado(websocket)`."""
    if not esta_autenticado(request):
        raise HTTPException(status_code=401, detail="Inicia sesion para continuar")
