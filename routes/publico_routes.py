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

# Los avisos describen a los proveedores por CATEGORIA, sin nombrarlos: la
# ley pide informar las transferencias a terceros, no identificar a cada
# encargado que procesa datos por cuenta de Sianka o del restaurante.
CATEGORIAS_PROVEEDORES = [
    "Telefonia, para recibir las llamadas",
    "Procesamiento de voz y de lenguaje, para entender y atender el pedido",
    "Alojamiento en la nube, para guardar pedidos y llamadas",
]


def _contexto(request: Request, ruta: str, titulo: str, descripcion: str, **extra) -> dict:
    return {
        "titulo": titulo,
        "descripcion": descripcion,
        "canonical": sitio.url(ruta),
        "sitio": sitio,
        "categorias_proveedores": CATEGORIAS_PROVEEDORES,
        "anio": date.today().year,
        **extra,
    }


@router.get("/privacidad")
async def aviso_privacidad(request: Request):
    # Sin lista de restaurantes: publicarla expondria la cartera de clientes.
    return templates.TemplateResponse(
        request,
        "publico/privacidad.html",
        _contexto(
            request,
            "/privacidad",
            "Aviso de privacidad",
            "Como Sianka protege los datos personales de los restaurantes que usan la plataforma "
            "y de las personas que llaman para hacer un pedido.",
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
            # Accesible por enlace directo (el restaurante lo publica en su
            # menu o redes), pero fuera de buscadores y del sitemap.
            robots="noindex, follow",
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
    # Los avisos por restaurante no se listan (no exponer la cartera de clientes).
    rutas = ["/privacidad", "/terminos"]
    urls = "".join(f"  <url><loc>{escape(sitio.url(ruta))}</loc></url>\n" for ruta in rutas)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")
