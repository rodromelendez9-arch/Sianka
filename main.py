import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Debe ir ANTES de importar las rutas: varios servicios leen sus variables
# con os.getenv() al importarse (p. ej. TWILIO_AUTH_TOKEN en twilio_routes).
load_dotenv()

from database import supabase_client  # noqa: E402
from routes import auth_routes, dashboard_routes, order_routes, publico_routes, twilio_routes  # noqa: E402
from services import cifrado_service, registro, sitio  # noqa: E402

registro.configurar()
logger = logging.getLogger(__name__)

INTERVALO_PURGA_SEGUNDOS = 24 * 60 * 60


async def _purgar_transcripciones_periodicamente() -> None:
    """Politica de retencion: una vez al dia borra las transcripciones mas
    viejas que RETENCION_TRANSCRIPCIONES_DIAS, y las direcciones y telefonos
    de entrega de ordenes igual de viejas. Es idempotente, asi que no
    importa si corren varios procesos a la vez."""
    while True:
        try:
            limite = datetime.now(timezone.utc) - timedelta(days=sitio.RETENCION_TRANSCRIPCIONES_DIAS)
            borradas = await asyncio.to_thread(supabase_client.purgar_transcripciones, limite.isoformat())
            entregas = await asyncio.to_thread(supabase_client.purgar_datos_entrega, limite.isoformat())
            if borradas or entregas:
                logger.info("Retencion: %s transcripciones y %s direcciones borradas", borradas, entregas)
        except Exception:
            logger.exception("Fallo la purga de transcripciones; se reintenta en 24 h")
        await asyncio.sleep(INTERVALO_PURGA_SEGUNDOS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sin clave de cifrado el servidor NO arranca: aceptaria llamadas y
    # fallaria al guardar datos personales (o, peor, los guardaria en claro).
    cifrado_service.verificar_configuracion()
    tarea_purga = asyncio.create_task(_purgar_transcripciones_periodicamente())
    yield
    tarea_purga.cancel()


app = FastAPI(title="Sianka - Voice Agent", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def redirigir_a_login(request: Request, exc: HTTPException):
    """Sin sesion, las PAGINAS del dashboard mandan al login en vez de mostrar
    un JSON de error; la API (/api/*) sigue respondiendo 401 para el JS."""
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url="/login", status_code=303)
    return await http_exception_handler(request, exc)


HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "true").lower() != "false"

# SESSION_SECRET_KEY debe ser fijo en produccion (si cambia, se cierran todas
# las sesiones activas). El fallback aleatorio solo es para no tronar en
# desarrollo si alguien olvida configurarlo.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY") or secrets.token_hex(32),
    same_site="lax",
    https_only=HTTPS_ONLY,
)

# Segunda linea de defensa ademas de escapar bien el HTML: si algun dia se
# reintroduce una fuga de XSS, un CSP sin scripts/estilos externos limita
# mucho lo que ese script inyectado puede hacer (no puede cargar JS de otro
# dominio, ni exfiltrar via fetch a otro origen). Por eso todo el JS del
# dashboard vive en archivos propios en /static -- nada de <script> inline.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

# Paginas que se pueden guardar en cache: las publicas y los archivos
# estaticos. Todo lo demas (dashboard, API) contiene datos personales y no
# debe quedarse en la cache del navegador ni de proxies intermedios.
_RUTAS_CACHEABLES = ("/static/", "/privacidad", "/terminos", "/robots.txt", "/sitemap.xml")


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    if request.url.path.startswith("/static/"):
        # Revalidar siempre (ETag -> 304 si no cambio): tras un deploy, los
        # paneles de los restaurantes toman el JS/CSS nuevo sin vaciar cache.
        response.headers["Cache-Control"] = "no-cache"
    elif not request.url.path.startswith(_RUTAS_CACHEABLES):
        response.headers["Cache-Control"] = "no-store"
    if HTTPS_ONLY:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(dashboard_routes.router_ws)
app.include_router(order_routes.router)
app.include_router(twilio_routes.router)
# Avisos de privacidad, terminos, robots.txt y sitemap.xml
app.include_router(publico_routes.router)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    """Para monitoreo de uptime (UptimeRobot, Better Uptime, un load balancer, etc)."""
    return "ok"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
    )
