import os
import secrets

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

# Debe ir ANTES de importar las rutas: varios servicios leen sus variables
# con os.getenv() al importarse (p. ej. DASHBOARD_PASSWORD en auth_service).
load_dotenv()

from routes import auth_routes, dashboard_routes, order_routes, twilio_routes  # noqa: E402

app = FastAPI(title="Voice Agent - Tacos El Güero")

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


@app.middleware("http")
async def cabeceras_de_seguridad(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if HTTPS_ONLY:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(dashboard_routes.router_ws)
app.include_router(order_routes.router)
app.include_router(twilio_routes.router)


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    """Este dashboard es una herramienta privada de operacion, no un sitio
    publico -- no debe aparecer en buscadores. Ver tambien el meta robots
    noindex en templates/base.html (defensa en dos capas)."""
    return "User-agent: *\nDisallow: /\n"


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
