from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from database import supabase_client
from models.order import OrdenStatusUpdate
from models.restaurant import DisponibilidadUpdate, PlatilloCreate, PlatilloUpdate
from services.auth_service import require_login
from services.prediccion_service import calcular_prediccion_demanda
from services.rate_limit_service import limitar
from services.reportes_service import calcular_reporte
from services.websocket_manager import manager

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_login), Depends(limitar(120, 60))],
)

# Cada endpoint recibe `restaurante_id` de la sesion (require_login) y TODA
# lectura/escritura se acota a ese restaurante: pasar el id de una orden o
# platillo de otro restaurante simplemente da 404.


@router.get("/ordenes")
async def listar_ordenes_activas(restaurante_id: str = Depends(require_login)) -> list[dict]:
    return supabase_client.get_ordenes_activas(restaurante_id)


@router.post("/ordenes/{orden_id}/status")
async def actualizar_status(
    orden_id: str, body: OrdenStatusUpdate, restaurante_id: str = Depends(require_login)
) -> dict:
    orden = supabase_client.actualizar_status_orden(orden_id, restaurante_id, body.status.value)
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    await manager.broadcast(
        restaurante_id,
        {
            "evento": "orden_actualizada",
            "orden_id": orden_id,
            "status": body.status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    return orden


@router.get("/resumen")
async def resumen_del_dia(restaurante_id: str = Depends(require_login)) -> dict:
    return supabase_client.get_resumen_del_dia(restaurante_id)


DIAS_POR_PERIODO = {"semana": 7, "mes": 30, "todo": 3650}


@router.get("/reportes")
async def reportes(
    periodo: Literal["semana", "mes", "todo"] = "semana",
    restaurante_id: str = Depends(require_login),
) -> dict:
    desde = datetime.now(timezone.utc) - timedelta(days=DIAS_POR_PERIODO[periodo])
    desde_iso = desde.isoformat()

    ordenes = supabase_client.get_ordenes_periodo(restaurante_id, desde_iso)
    llamadas = supabase_client.get_llamadas_periodo(restaurante_id, desde_iso)

    reporte = calcular_reporte(ordenes, llamadas)
    reporte["periodo"] = periodo
    return reporte


SEMANAS_HISTORIAL_PREDICCION = 8


@router.get("/prediccion")
async def prediccion_demanda(restaurante_id: str = Depends(require_login)) -> dict:
    desde = datetime.now(timezone.utc) - timedelta(weeks=SEMANAS_HISTORIAL_PREDICCION)
    desde_iso = desde.isoformat()

    ordenes = supabase_client.get_ordenes_periodo(restaurante_id, desde_iso)
    llamadas = supabase_client.get_llamadas_periodo(restaurante_id, desde_iso)

    return {
        "pronostico": calcular_prediccion_demanda(ordenes, llamadas),
        "semanas_historial": SEMANAS_HISTORIAL_PREDICCION,
    }


@router.get("/llamadas")
async def listar_llamadas(limite: int = 50, restaurante_id: str = Depends(require_login)) -> list[dict]:
    limite = max(1, min(limite, 200))
    return supabase_client.get_llamadas(restaurante_id, limite)


@router.get("/menu")
async def listar_menu(restaurante_id: str = Depends(require_login)) -> list[dict]:
    return supabase_client.get_menu(restaurante_id)


@router.post("/menu")
async def crear_platillo(body: PlatilloCreate, restaurante_id: str = Depends(require_login)) -> dict:
    return supabase_client.crear_platillo(
        restaurante_id=restaurante_id,
        platillo=body.platillo,
        precio=body.precio,
        ingredientes=body.ingredientes or "",
    )


@router.put("/menu/{menu_id}")
async def actualizar_platillo(
    menu_id: str, body: PlatilloUpdate, restaurante_id: str = Depends(require_login)
) -> dict:
    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    platillo = supabase_client.actualizar_platillo(menu_id, restaurante_id, **campos)
    if not platillo:
        raise HTTPException(status_code=404, detail="Platillo no encontrado")
    return platillo


@router.delete("/menu/{menu_id}")
async def eliminar_platillo(menu_id: str, restaurante_id: str = Depends(require_login)) -> dict:
    if not supabase_client.eliminar_platillo(menu_id, restaurante_id):
        raise HTTPException(status_code=404, detail="Platillo no encontrado")
    return {"eliminado": True}


@router.post("/menu/{menu_id}/disponibilidad")
async def actualizar_disponibilidad(
    menu_id: str, body: DisponibilidadUpdate, restaurante_id: str = Depends(require_login)
) -> dict:
    platillo = supabase_client.actualizar_disponibilidad(menu_id, restaurante_id, body.disponible)
    if not platillo:
        raise HTTPException(status_code=404, detail="Platillo no encontrado")
    return platillo
