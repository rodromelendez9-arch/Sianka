import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates

from database import supabase_client
from prompts.agent_prompt import TIEMPO_RECOLECCION_DEFAULT, aviso_privacidad_breve, saludo_inicial
from routes.order_routes import DIAS_POR_PERIODO, SEMANAS_HISTORIAL_PREDICCION
from services.auth_service import require_login, restaurante_de_sesion
from services.cifrado_service import enmascarar_telefono
from services.prediccion_service import calcular_prediccion_demanda
from services.reportes_service import calcular_reporte
from services.websocket_manager import manager

# Cada ruta recibe `restaurante_id` de la sesion (ver require_login): todas
# las consultas se filtran por el restaurante del usuario que inicio sesion.
router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["enmascarar"] = enmascarar_telefono

# Router separado: `require_login` depende de `Request` y no se resuelve en
# conexiones WebSocket (ver auth_service.py). La sesion se valida a mano
# dentro del handler con restaurante_de_sesion().
router_ws = APIRouter()


@router.get("/")
async def dashboard(request: Request, restaurante_id: str = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "restaurante": supabase_client.get_restaurante(restaurante_id),
            "ordenes_activas": supabase_client.get_ordenes_activas(restaurante_id),
            "resumen": supabase_client.get_resumen_del_dia(restaurante_id),
            "active_page": "dashboard",
        },
    )


@router.get("/llamadas")
async def llamadas_page(request: Request, restaurante_id: str = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "llamadas.html",
        {
            "restaurante": supabase_client.get_restaurante(restaurante_id),
            "llamadas": supabase_client.get_llamadas(restaurante_id, limite=100),
            "active_page": "llamadas",
        },
    )


@router.get("/menu")
async def menu_page(request: Request, restaurante_id: str = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "menu.html",
        {
            "restaurante": supabase_client.get_restaurante(restaurante_id),
            "menu": supabase_client.get_menu(restaurante_id),
            "active_page": "menu",
        },
    )


@router.get("/reportes")
async def reportes_page(
    request: Request,
    periodo: str = "semana",
    restaurante_id: str = Depends(require_login),
):
    if periodo not in DIAS_POR_PERIODO:
        periodo = "semana"

    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_POR_PERIODO[periodo])
    ordenes = supabase_client.get_ordenes_periodo(restaurante_id, desde.isoformat())
    llamadas = supabase_client.get_llamadas_periodo(restaurante_id, desde.isoformat())
    reporte = calcular_reporte(ordenes, llamadas)
    reporte["periodo"] = periodo

    desde_prediccion = datetime.now(timezone.utc) - timedelta(weeks=SEMANAS_HISTORIAL_PREDICCION)
    ordenes_historial = supabase_client.get_ordenes_periodo(restaurante_id, desde_prediccion.isoformat())
    llamadas_historial = supabase_client.get_llamadas_periodo(restaurante_id, desde_prediccion.isoformat())
    pronostico = calcular_prediccion_demanda(ordenes_historial, llamadas_historial)

    return templates.TemplateResponse(
        request,
        "reportes.html",
        {
            "restaurante": supabase_client.get_restaurante(restaurante_id),
            "reporte": reporte,
            "pronostico": pronostico,
            "active_page": "reportes",
        },
    )


# ---------------- Configuracion del restaurante ----------------

def _render_configuracion(request: Request, restaurante: dict, mensaje: str = "", error: str = ""):
    return templates.TemplateResponse(
        request,
        "configuracion.html",
        {
            "restaurante": restaurante,
            "saludo_default": saludo_inicial({"nombre": restaurante.get("nombre")}),
            "aviso_breve": aviso_privacidad_breve(),
            "datos_legales_completos": all(
                restaurante.get(c) for c in ("razon_social", "domicilio", "email_privacidad")
            ),
            "tiempo_default": TIEMPO_RECOLECCION_DEFAULT,
            "mensaje": mensaje,
            "error": error,
            "active_page": "configuracion",
        },
        status_code=400 if error else 200,
    )


@router.get("/configuracion")
async def configuracion_page(request: Request, restaurante_id: str = Depends(require_login)):
    return _render_configuracion(request, supabase_client.get_restaurante(restaurante_id))


@router.post("/configuracion")
async def configuracion_guardar(
    request: Request,
    nombre: str = Form(...),
    ciudad: str = Form(""),
    horario: str = Form(""),
    saludo: str = Form(""),
    tiempo_recoleccion_min: int = Form(TIEMPO_RECOLECCION_DEFAULT),
    instrucciones_extra: str = Form(""),
    razon_social: str = Form(""),
    domicilio: str = Form(""),
    email_privacidad: str = Form(""),
    restaurante_id: str = Depends(require_login),
):
    # El slug y el numero de Twilio NO se editan aqui: el numero decide que
    # restaurante contesta cada llamada, y cambiarlo sin tocar Twilio dejaria
    # al restaurante sin llamadas. Esos se cambian con admin.py.
    restaurante = supabase_client.get_restaurante(restaurante_id)

    nombre = nombre.strip()
    if not nombre:
        return _render_configuracion(request, restaurante, error="El nombre no puede quedar vacio.")
    if not 1 <= tiempo_recoleccion_min <= 180:
        return _render_configuracion(
            request, restaurante, error="El tiempo de recoleccion debe estar entre 1 y 180 minutos."
        )

    email_privacidad = email_privacidad.strip().lower()
    if email_privacidad and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_privacidad):
        return _render_configuracion(
            request, restaurante, error="El correo de privacidad no parece valido."
        )

    restaurante = supabase_client.actualizar_restaurante(
        restaurante_id,
        nombre=nombre[:120],
        ciudad=ciudad.strip()[:120],
        horario=horario.strip()[:300],
        # Vacio = usar el saludo por defecto (que ya incluye el nombre). El
        # aviso de privacidad se agrega siempre despues, no es editable.
        saludo=saludo.strip()[:300] or None,
        tiempo_recoleccion_min=tiempo_recoleccion_min,
        instrucciones_extra=instrucciones_extra.strip()[:2000] or None,
        razon_social=razon_social.strip()[:200] or None,
        domicilio=domicilio.strip()[:300] or None,
        email_privacidad=email_privacidad[:200] or None,
    )
    return _render_configuracion(
        request, restaurante, mensaje="Cambios guardados. Aplican desde la siguiente llamada."
    )


@router_ws.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    restaurante_id = restaurante_de_sesion(websocket)
    if not restaurante_id:
        await websocket.close(code=1008)
        return

    await manager.connect(restaurante_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(restaurante_id, websocket)
