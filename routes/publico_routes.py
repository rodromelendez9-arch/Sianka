"""Paginas publicas: avisos de privacidad, terminos, robots.txt y sitemap.

Son las unicas paginas que los buscadores deben indexar; el dashboard sigue
con noindex y bloqueado en robots.txt."""
from datetime import date
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.templating import Jinja2Templates

from database import supabase_client
from services import sitio

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PROVEEDORES = [
    {"nombre": "Twilio Inc.", "funcion": "Telefonia: recibe la llamada y transmite el audio", "pais": "Estados Unidos"},
    {"nombre": "Deepgram, Inc.", "funcion": "Convierte la voz a texto y el texto a voz", "pais": "Estados Unidos"},
    {"nombre": "Anthropic, PBC", "funcion": "Interpreta la conversacion para tomar el pedido", "pais": "Estados Unidos"},
    {"nombre": "Supabase, Inc.", "funcion": "Base de datos donde se guardan pedidos y llamadas", "pais": "Estados Unidos"},
]


def _contexto(request: Request, ruta: str, titulo: str, descripcion: str, **extra) -> dict:
    return {
        "titulo": titulo,
        "descripcion": descripcion,
        "canonical": sitio.url(ruta),
        "sitio": sitio,
        "proveedores": PROVEEDORES,
        "anio": date.today().year,
        **extra,
    }


@router.get("/privacidad")
async def aviso_privacidad(request: Request):
    restaurantes = [r for r in supabase_client.listar_restaurantes() if r.get("activo")]
    return templates.TemplateResponse(
        request,
        "publico/privacidad.html",
        _contexto(
            request,
            "/privacidad",
            "Aviso de privacidad",
            "Como Sianka protege los datos personales de los restaurantes que usan la plataforma "
            "y de las personas que llaman para hacer un pedido.",
            restaurantes=restaurantes,
        ),
    )


@router.get("/privacidad/{slug}")
async def aviso_privacidad_restaurante(request: Request, slug: str):
    restaurante = supabase_client.get_restaurante_by_slug(slug)
    if not restaurante or not restaurante.get("activo"):
        raise HTTPException(status_code=404, detail="Restaurante no encontrado")
    return templates.TemplateResponse(
        request,
        "publico/privacidad_restaurante.html",
        _contexto(
            request,
            f"/privacidad/{slug}",
            f"Aviso de privacidad de {restaurante['nombre']}",
            f"Como {restaurante['nombre']} usa y protege los datos de las personas que llaman "
            "para hacer un pedido por telefono.",
            restaurante=restaurante,
        ),
    )


@router.get("/terminos")
async def terminos(request: Request):
    return templates.TemplateResponse(
        request,
        "publico/terminos.html",
        _contexto(
            request,
            "/terminos",
            "Terminos de servicio",
            "Condiciones de uso de Sianka, el asistente de voz que toma pedidos por telefono para restaurantes.",
        ),
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    """Solo las paginas publicas se indexan. El dashboard es una herramienta
    privada (ademas lleva meta noindex en templates/base.html)."""
    return (
        "User-agent: *\n"
        "Allow: /privacidad\n"
        "Allow: /terminos\n"
        "Disallow: /\n"
        f"\nSitemap: {sitio.url('/sitemap.xml')}\n"
    )


@router.get("/sitemap.xml")
async def sitemap() -> Response:
    rutas = ["/privacidad", "/terminos"]
    rutas += [f"/privacidad/{r['slug']}" for r in supabase_client.listar_restaurantes() if r.get("activo")]
    urls = "".join(f"  <url><loc>{escape(sitio.url(ruta))}</loc></url>\n" for ruta in rutas)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
