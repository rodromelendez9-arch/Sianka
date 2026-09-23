import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from services.auth_service import cerrar_sesion, iniciar_sesion, verificar_password

router = APIRouter()
templates = Jinja2Templates(directory="templates")

INTENTOS_MAX = 5
VENTANA_SEGUNDOS = 300

# Cuenta solo intentos FALLIDOS por IP (no cada peticion) porque un empleado
# escribiendo su contrasena bien no deberia acercarse nunca al limite; esto
# es para frenar fuerza bruta, no trafico normal.
_intentos_fallidos: dict[str, list[float]] = {}


def _ip_bloqueada(ip: str) -> bool:
    ahora = time.monotonic()
    intentos = [t for t in _intentos_fallidos.get(ip, []) if ahora - t < VENTANA_SEGUNDOS]
    _intentos_fallidos[ip] = intentos
    return len(intentos) >= INTENTOS_MAX


def _registrar_intento_fallido(ip: str) -> None:
    _intentos_fallidos.setdefault(ip, []).append(time.monotonic())


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    ip = request.client.host if request.client else "desconocido"

    if _ip_bloqueada(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo."},
            status_code=429,
        )

    if not verificar_password(password):
        _registrar_intento_fallido(ip)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Contrasena incorrecta"},
            status_code=401,
        )

    iniciar_sesion(request)
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    cerrar_sesion(request)
    return RedirectResponse(url="/login", status_code=303)
