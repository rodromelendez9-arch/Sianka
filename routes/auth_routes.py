import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from services.auth_service import autenticar, cerrar_sesion, iniciar_sesion

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
    return templates.TemplateResponse(request, "login.html", {"error": None, "email": ""})


@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    ip = request.client.host if request.client else "desconocido"

    if _ip_bloqueada(ip):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Demasiados intentos fallidos. Espera unos minutos e intenta de nuevo.", "email": email},
            status_code=429,
        )

    usuario = autenticar(email, password)
    if not usuario:
        _registrar_intento_fallido(ip)
        # Mismo mensaje exista o no el correo: no revela quien tiene cuenta.
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Correo o contrasena incorrectos", "email": email},
            status_code=401,
        )

    iniciar_sesion(request, usuario)
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    cerrar_sesion(request)
    return RedirectResponse(url="/login", status_code=303)
