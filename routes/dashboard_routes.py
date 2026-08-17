from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates

from database import supabase_client
from services.websocket_manager import manager

router = APIRouter()
templates = Jinja2Templates(directory="templates")


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


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
