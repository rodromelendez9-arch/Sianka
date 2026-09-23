from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates

from database import supabase_client
from routes.order_routes import DIAS_POR_PERIODO, SEMANAS_HISTORIAL_PREDICCION
from services.auth_service import esta_autenticado, require_login
from services.prediccion_service import calcular_prediccion_demanda
from services.reportes_service import calcular_reporte
from services.websocket_manager import manager

router = APIRouter(dependencies=[Depends(require_login)])
templates = Jinja2Templates(directory="templates")

# Router separado y SIN el Depends(require_login) de arriba: ese depende de
# `Request` y no se resuelve en conexiones WebSocket (ver auth_service.py).
# La sesion se valida a mano dentro del handler con esta_autenticado().
router_ws = APIRouter()


@router.get("/")
async def dashboard(request: Request):
    restaurante = supabase_client.get_restaurante_activo()
    ordenes_activas: list[dict] = []
    resumen = {"llamadas": 0, "ordenes": 0, "ingreso_total": 0.0, "conversion": 0.0}

    if restaurante:
        ordenes_activas = supabase_client.get_ordenes_activas(restaurante["id"])
        resumen = supabase_client.get_resumen_del_dia(restaurante["id"])

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "restaurante": restaurante,
            "ordenes_activas": ordenes_activas,
            "resumen": resumen,
            "active_page": "dashboard",
        },
    )


@router.get("/llamadas")
async def llamadas_page(request: Request):
    restaurante = supabase_client.get_restaurante_activo()
    llamadas: list[dict] = []

    if restaurante:
        llamadas = supabase_client.get_llamadas(restaurante["id"], limite=100)

    return templates.TemplateResponse(
        request,
        "llamadas.html",
        {
            "restaurante": restaurante,
            "llamadas": llamadas,
            "active_page": "llamadas",
        },
    )


@router.get("/menu")
async def menu_page(request: Request):
    restaurante = supabase_client.get_restaurante_activo()
    menu: list[dict] = []

    if restaurante:
        menu = supabase_client.get_menu(restaurante["id"])

    return templates.TemplateResponse(
        request,
        "menu.html",
        {
            "restaurante": restaurante,
            "menu": menu,
            "active_page": "menu",
        },
    )


@router.get("/reportes")
async def reportes_page(request: Request, periodo: str = "semana"):
    if periodo not in DIAS_POR_PERIODO:
        periodo = "semana"

    restaurante = supabase_client.get_restaurante_activo()
    reporte = {
        "total_ordenes": 0,
        "total_llamadas": 0,
        "ingreso_total": 0.0,
        "ticket_promedio": 0.0,
        "platillo_top": None,
        "hora_pico": None,
        "dia_mas_fuerte": None,
        "periodo": periodo,
    }

    pronostico: list[dict] = []

    if restaurante:
        desde = datetime.now(timezone.utc) - timedelta(days=DIAS_POR_PERIODO[periodo])
        ordenes = supabase_client.get_ordenes_periodo(restaurante["id"], desde.isoformat())
        llamadas = supabase_client.get_llamadas_periodo(restaurante["id"], desde.isoformat())
        reporte = calcular_reporte(ordenes, llamadas)
        reporte["periodo"] = periodo

        desde_prediccion = datetime.now(timezone.utc) - timedelta(weeks=SEMANAS_HISTORIAL_PREDICCION)
        ordenes_historial = supabase_client.get_ordenes_periodo(restaurante["id"], desde_prediccion.isoformat())
        llamadas_historial = supabase_client.get_llamadas_periodo(restaurante["id"], desde_prediccion.isoformat())
        pronostico = calcular_prediccion_demanda(ordenes_historial, llamadas_historial)

    return templates.TemplateResponse(
        request,
        "reportes.html",
        {
            "restaurante": restaurante,
            "reporte": reporte,
            "pronostico": pronostico,
            "active_page": "reportes",
        },
    )


@router_ws.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    if not esta_autenticado(websocket):
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
