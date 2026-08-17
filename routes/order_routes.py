from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from database import supabase_client
from models.order import OrdenStatusUpdate
from models.restaurant import PlatilloCreate, PlatilloUpdate
from services.websocket_manager import manager

router = APIRouter(prefix="/api")


def _restaurante_activo_id() -> str:
    restaurante = supabase_client.get_restaurante_activo()
    if not restaurante:
        raise HTTPException(status_code=404, detail="No hay un restaurante activo configurado")
    return restaurante["id"]


@router.get("/ordenes")
async def listar_ordenes_activas() -> list[dict]:
    restaurante_id = _restaurante_activo_id()
    return supabase_client.get_ordenes_activas(restaurante_id)


@router.post("/ordenes/{orden_id}/status")
async def actualizar_status(orden_id: str, body: OrdenStatusUpdate) -> dict:
    orden = supabase_client.actualizar_status_orden(orden_id, body.status.value)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    await manager.broadcast(
        {
            "evento": "orden_actualizada",
            "orden_id": orden_id,
            "status": body.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    return orden


@router.get("/resumen")
async def resumen_del_dia() -> dict:
    restaurante_id = _restaurante_activo_id()
    return supabase_client.get_resumen_del_dia(restaurante_id)


@router.get("/llamadas")
async def listar_llamadas(limite: int = 50) -> list[dict]:
    restaurante_id = _restaurante_activo_id()
    return supabase_client.get_llamadas(restaurante_id, limite)


@router.get("/menu")
async def listar_menu() -> list[dict]:
    restaurante_id = _restaurante_activo_id()
    return supabase_client.get_menu(restaurante_id)


@router.post("/menu")
async def crear_platillo(body: PlatilloCreate) -> dict:
    restaurante_id = _restaurante_activo_id()
    return supabase_client.crear_platillo(
        restaurante_id=restaurante_id,
        platillo=body.platillo,
        precio=body.precio,
        ingredientes=body.ingredientes or "",
    )


@router.put("/menu/{menu_id}")
async def actualizar_platillo(menu_id: str, body: PlatilloUpdate) -> dict:
    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    platillo = supabase_client.actualizar_platillo(menu_id, **campos)
    if not platillo:
        raise HTTPException(status_code=404, detail="Platillo no encontrado")
    return platillo


@router.delete("/menu/{menu_id}")
async def eliminar_platillo(menu_id: str) -> dict:
    supabase_client.eliminar_platillo(menu_id)
    return {"eliminado": True}
