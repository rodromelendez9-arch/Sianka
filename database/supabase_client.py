import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL y SUPABASE_KEY deben estar configurados en .env")
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ---------------- Restaurantes ----------------

def get_restaurante_activo() -> Optional[dict]:
    client = get_client()
    response = (
        client.table("restaurantes")
        .select("*")
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    data = response.data
    return data[0] if data else None


def get_restaurante_by_twilio_number(twilio_number: str) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("restaurantes")
        .select("*")
        .eq("twilio_number", twilio_number)
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    data = response.data
    return data[0] if data else None


# ---------------- Menu ----------------

def get_menu(restaurante_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("menus")
        .select("*")
        .eq("restaurante_id", restaurante_id)
        .eq("activo", True)
        .order("platillo")
        .execute()
    )
    return response.data or []


def crear_platillo(restaurante_id: str, platillo: str, precio: float, ingredientes: str = "") -> dict:
    client = get_client()
    response = (
        client.table("menus")
        .insert(
            {
                "restaurante_id": restaurante_id,
                "platillo": platillo,
                "precio": precio,
                "ingredientes": ingredientes,
                "activo": True,
            }
        )
        .execute()
    )
    return response.data[0]


def actualizar_platillo(menu_id: str, **campos) -> Optional[dict]:
    client = get_client()
    response = client.table("menus").update(campos).eq("id", menu_id).execute()
    return response.data[0] if response.data else None


def eliminar_platillo(menu_id: str) -> None:
    client = get_client()
    client.table("menus").update({"activo": False}).eq("id", menu_id).execute()


# ---------------- Llamadas ----------------

def crear_llamada(restaurante_id: str, telefono_cliente: str) -> dict:
    client = get_client()
    response = (
        client.table("llamadas")
        .insert(
            {
                "restaurante_id": restaurante_id,
                "telefono_cliente": telefono_cliente,
            }
        )
        .execute()
    )
    return response.data[0]


def actualizar_llamada(llamada_id: str, **campos) -> Optional[dict]:
    client = get_client()
    response = client.table("llamadas").update(campos).eq("id", llamada_id).execute()
    return response.data[0] if response.data else None


def get_llamadas(restaurante_id: str, limite: int = 50) -> list[dict]:
    client = get_client()
    response = (
        client.table("llamadas")
        .select("*")
        .eq("restaurante_id", restaurante_id)
        .order("created_at", desc=True)
        .limit(limite)
        .execute()
    )
    return response.data or []


# ---------------- Ordenes ----------------

def crear_orden(
    restaurante_id: str,
    llamada_id: Optional[str],
    items: list[dict],
    total: float,
    tiempo_recoleccion: str = "20 minutos",
) -> dict:
    client = get_client()
    response = (
        client.table("ordenes")
        .insert(
            {
                "restaurante_id": restaurante_id,
                "llamada_id": llamada_id,
                "items": items,
                "total": total,
                "tiempo_recoleccion": tiempo_recoleccion,
                "status": "nueva",
            }
        )
        .execute()
    )
    return response.data[0]


def actualizar_status_orden(orden_id: str, status: str) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("ordenes")
        .update({"status": status})
        .eq("id", orden_id)
        .execute()
    )
    return response.data[0] if response.data else None


def get_ordenes_activas(restaurante_id: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("ordenes")
        .select("*")
        .eq("restaurante_id", restaurante_id)
        .neq("status", "entregada")
        .order("created_at", desc=False)
        .execute()
    )
    return response.data or []


def get_orden(orden_id: str) -> Optional[dict]:
    client = get_client()
    response = client.table("ordenes").select("*").eq("id", orden_id).limit(1).execute()
    data = response.data
    return data[0] if data else None


# ---------------- Resumen del dia ----------------

def get_resumen_del_dia(restaurante_id: str) -> dict:
    client = get_client()
    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    llamadas_response = (
        client.table("llamadas")
        .select("id", count="exact")
        .eq("restaurante_id", restaurante_id)
        .gte("created_at", f"{hoy}T00:00:00")
        .execute()
    )
    total_llamadas = llamadas_response.count or 0

    ordenes_response = (
        client.table("ordenes")
        .select("total")
        .eq("restaurante_id", restaurante_id)
        .gte("created_at", f"{hoy}T00:00:00")
        .execute()
    )
    ordenes_hoy = ordenes_response.data or []
    total_ordenes = len(ordenes_hoy)
    ingreso_total = sum(float(o["total"] or 0) for o in ordenes_hoy)
    conversion = round((total_ordenes / total_llamadas * 100), 1) if total_llamadas else 0.0

    return {
        "llamadas": total_llamadas,
        "ordenes": total_ordenes,
        "ingreso_total": ingreso_total,
        "conversion": conversion,
    }
