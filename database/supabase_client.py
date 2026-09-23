import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from services import cifrado_service

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

def get_restaurante(restaurante_id: str) -> Optional[dict]:
    client = get_client()
    response = client.table("restaurantes").select("*").eq("id", restaurante_id).limit(1).execute()
    data = response.data
    return data[0] if data else None


def get_restaurante_by_slug(slug: str) -> Optional[dict]:
    client = get_client()
    response = client.table("restaurantes").select("*").eq("slug", slug).limit(1).execute()
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


def listar_restaurantes() -> list[dict]:
    client = get_client()
    response = client.table("restaurantes").select("*").order("created_at").execute()
    return response.data or []


def crear_restaurante(**campos) -> dict:
    client = get_client()
    response = client.table("restaurantes").insert(campos).execute()
    return response.data[0]


def actualizar_restaurante(restaurante_id: str, **campos) -> Optional[dict]:
    client = get_client()
    response = client.table("restaurantes").update(campos).eq("id", restaurante_id).execute()
    return response.data[0] if response.data else None


# ---------------- Usuarios ----------------

def get_usuario_por_email(email: str) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("usuarios")
        .select("*")
        .eq("email", email.strip().lower())
        .eq("activo", True)
        .limit(1)
        .execute()
    )
    data = response.data
    return data[0] if data else None


def crear_usuario(restaurante_id: str, email: str, password_hash: str, nombre: str = "") -> dict:
    client = get_client()
    response = (
        client.table("usuarios")
        .insert(
            {
                "restaurante_id": restaurante_id,
                "email": email.strip().lower(),
                "password_hash": password_hash,
                "nombre": nombre,
            }
        )
        .execute()
    )
    return response.data[0]


def actualizar_password_usuario(email: str, password_hash: str) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("usuarios")
        .update({"password_hash": password_hash})
        .eq("email", email.strip().lower())
        .execute()
    )
    return response.data[0] if response.data else None


# ---------------- Menu ----------------

def get_menu(restaurante_id: str) -> list[dict]:
    """Todos los platillos activos, disponibles o no -- para la vista de administrador."""
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


def get_menu_disponible(restaurante_id: str) -> list[dict]:
    """Solo platillos con existencias -- lo que el agente de voz le puede ofrecer al cliente."""
    client = get_client()
    response = (
        client.table("menus")
        .select("*")
        .eq("restaurante_id", restaurante_id)
        .eq("activo", True)
        .eq("disponible", True)
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
                "disponible": True,
            }
        )
        .execute()
    )
    return response.data[0]


def actualizar_platillo(menu_id: str, restaurante_id: str, **campos) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("menus")
        .update(campos)
        .eq("id", menu_id)
        .eq("restaurante_id", restaurante_id)
        .execute()
    )
    return response.data[0] if response.data else None


def actualizar_disponibilidad(menu_id: str, restaurante_id: str, disponible: bool) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("menus")
        .update({"disponible": disponible})
        .eq("id", menu_id)
        .eq("restaurante_id", restaurante_id)
        .execute()
    )
    return response.data[0] if response.data else None


def eliminar_platillo(menu_id: str, restaurante_id: str) -> bool:
    client = get_client()
    response = (
        client.table("menus")
        .update({"activo": False})
        .eq("id", menu_id)
        .eq("restaurante_id", restaurante_id)
        .execute()
    )
    return bool(response.data)


# ---------------- Llamadas ----------------
#
# Los datos personales (telefono, nombre, transcripcion) se cifran aqui al
# escribir y se descifran al leer (ver services/cifrado_service.py): el resto
# del codigo trabaja con texto normal y la base nunca los guarda en claro.

CAMPOS_CIFRADOS_LLAMADA = ("telefono_cliente", "nombre_cliente", "transcripcion")
CAMPOS_CIFRADOS_ORDEN = ("nombre_cliente", "direccion_entrega", "referencias_entrega", "telefono_contacto")
# Datos que solo sirven para llevar el pedido: se borran con la retencion.
CAMPOS_ENTREGA = ("direccion_entrega", "referencias_entrega", "telefono_contacto", "paga_con")


def _descifrar_fila(fila: Optional[dict], campos: tuple[str, ...]) -> Optional[dict]:
    if fila:
        for campo in campos:
            if campo in fila:
                fila[campo] = cifrado_service.descifrar(fila[campo])
    return fila


def _cifrar_campos(campos: dict, cifrables: tuple[str, ...]) -> dict:
    return {k: (cifrado_service.cifrar(v) if k in cifrables else v) for k, v in campos.items()}


def crear_llamada(restaurante_id: str, telefono_cliente: str) -> dict:
    client = get_client()
    response = (
        client.table("llamadas")
        .insert(
            {
                "restaurante_id": restaurante_id,
                "telefono_cliente": cifrado_service.cifrar(telefono_cliente),
                "telefono_hash": cifrado_service.huella_telefono(telefono_cliente),
            }
        )
        .execute()
    )
    return _descifrar_fila(response.data[0], CAMPOS_CIFRADOS_LLAMADA)


def actualizar_llamada(llamada_id: str, **campos) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("llamadas")
        .update(_cifrar_campos(campos, CAMPOS_CIFRADOS_LLAMADA))
        .eq("id", llamada_id)
        .execute()
    )
    return _descifrar_fila(response.data[0], CAMPOS_CIFRADOS_LLAMADA) if response.data else None


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
    return [_descifrar_fila(f, CAMPOS_CIFRADOS_LLAMADA) for f in response.data or []]


# ---------------- Ordenes ----------------

def crear_orden(
    restaurante_id: str,
    llamada_id: Optional[str],
    items: list[dict],
    total: float,
    tiempo_recoleccion: str = "20 minutos",
    nombre_cliente: Optional[str] = None,
    tipo_entrega: str = "recoger",
    costo_envio: float = 0.0,
    **datos_entrega,
) -> dict:
    """`datos_entrega` (solo a domicilio): direccion_entrega,
    referencias_entrega, telefono_contacto, metodo_pago, paga_con."""
    client = get_client()
    fila = {
        "restaurante_id": restaurante_id,
        "llamada_id": llamada_id,
        "items": items,
        "total": total,
        "tiempo_recoleccion": tiempo_recoleccion,
        "nombre_cliente": nombre_cliente,
        "tipo_entrega": tipo_entrega,
        "costo_envio": costo_envio,
        "status": "nueva",
        **datos_entrega,
    }
    response = (
        client.table("ordenes")
        .insert(_cifrar_campos(fila, CAMPOS_CIFRADOS_ORDEN))
        .execute()
    )
    return _descifrar_fila(response.data[0], CAMPOS_CIFRADOS_ORDEN)


def actualizar_status_orden(orden_id: str, restaurante_id: str, status: str) -> Optional[dict]:
    client = get_client()
    response = (
        client.table("ordenes")
        .update({"status": status})
        .eq("id", orden_id)
        .eq("restaurante_id", restaurante_id)
        .execute()
    )
    return _descifrar_fila(response.data[0], CAMPOS_CIFRADOS_ORDEN) if response.data else None


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
    return [_descifrar_fila(f, CAMPOS_CIFRADOS_ORDEN) for f in response.data or []]


def get_orden(orden_id: str) -> Optional[dict]:
    client = get_client()
    response = client.table("ordenes").select("*").eq("id", orden_id).limit(1).execute()
    data = response.data
    return _descifrar_fila(data[0], CAMPOS_CIFRADOS_ORDEN) if data else None


# ---------------- Proteccion de datos (ARCO y retencion) ----------------

def get_llamadas_por_telefono(restaurante_id: str, telefono: str) -> list[dict]:
    """Todas las llamadas de un numero (buscadas por su huella), con sus
    ordenes. Para atender solicitudes de acceso de un cliente."""
    huella = cifrado_service.huella_telefono(telefono)
    if not huella:
        return []
    client = get_client()
    response = (
        client.table("llamadas")
        .select("*, ordenes(*)")
        .eq("restaurante_id", restaurante_id)
        .eq("telefono_hash", huella)
        .order("created_at")
        .execute()
    )
    llamadas = []
    for fila in response.data or []:
        _descifrar_fila(fila, CAMPOS_CIFRADOS_LLAMADA)
        for orden in fila.get("ordenes") or []:
            _descifrar_fila(orden, CAMPOS_CIFRADOS_ORDEN)
        llamadas.append(fila)
    return llamadas


def anonimizar_cliente(restaurante_id: str, telefono: str) -> int:
    """Cancelacion (derecho ARCO): borra telefono, nombre y transcripciones
    de ese cliente. Las ordenes se conservan sin datos personales (platillos
    y totales) porque el restaurante las necesita para su contabilidad.
    Devuelve cuantas llamadas se anonimizaron."""
    llamadas = get_llamadas_por_telefono(restaurante_id, telefono)
    client = get_client()
    for llamada in llamadas:
        client.table("llamadas").update(
            {"telefono_cliente": None, "telefono_hash": None, "nombre_cliente": None, "transcripcion": None}
        ).eq("id", llamada["id"]).execute()
        client.table("ordenes").update(
            {"nombre_cliente": None, **{campo: None for campo in CAMPOS_ENTREGA}}
        ).eq("llamada_id", llamada["id"]).execute()
    return len(llamadas)


def purgar_transcripciones(antes_de_iso: str) -> int:
    """Politica de retencion: la transcripcion solo sirve para revisar la
    llamada unos dias; despues se borra. Devuelve cuantas se borraron."""
    client = get_client()
    response = (
        client.table("llamadas")
        .update({"transcripcion": None})
        .lt("created_at", antes_de_iso)
        .not_.is_("transcripcion", "null")
        .execute()
    )
    return len(response.data or [])


def purgar_datos_entrega(antes_de_iso: str) -> int:
    """Politica de retencion: la direccion y el telefono de contacto solo
    sirven para llevar el pedido. Pasado el plazo se borran; la orden se
    conserva (platillos y totales) para reportes y contabilidad."""
    client = get_client()
    response = (
        client.table("ordenes")
        .update({campo: None for campo in CAMPOS_ENTREGA})
        .lt("created_at", antes_de_iso)
        .not_.is_("direccion_entrega", "null")
        .execute()
    )
    return len(response.data or [])


def cifrar_filas_existentes() -> dict[str, int]:
    """Migra filas guardadas antes del cifrado (texto plano) al formato
    cifrado. Idempotente: las ya cifradas se saltan."""
    client = get_client()
    conteo = {"llamadas": 0, "ordenes": 0}

    llamadas = (
        client.table("llamadas").select("id, telefono_cliente, nombre_cliente, transcripcion").execute().data or []
    )
    for fila in llamadas:
        cambios = {
            campo: cifrado_service.cifrar(fila[campo])
            for campo in CAMPOS_CIFRADOS_LLAMADA
            if fila.get(campo) and not cifrado_service.esta_cifrado(fila[campo])
        }
        if "telefono_cliente" in cambios:
            cambios["telefono_hash"] = cifrado_service.huella_telefono(fila["telefono_cliente"])
        if cambios:
            client.table("llamadas").update(cambios).eq("id", fila["id"]).execute()
            conteo["llamadas"] += 1

    ordenes = client.table("ordenes").select("id, " + ", ".join(CAMPOS_CIFRADOS_ORDEN)).execute().data or []
    for fila in ordenes:
        cambios = {
            campo: cifrado_service.cifrar(fila[campo])
            for campo in CAMPOS_CIFRADOS_ORDEN
            if fila.get(campo) and not cifrado_service.esta_cifrado(fila[campo])
        }
        if cambios:
            client.table("ordenes").update(cambios).eq("id", fila["id"]).execute()
            conteo["ordenes"] += 1

    return conteo


# ---------------- Reportes ----------------

def get_ordenes_periodo(restaurante_id: str, desde_iso: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("ordenes")
        .select("items, total, created_at")
        .eq("restaurante_id", restaurante_id)
        .gte("created_at", desde_iso)
        .execute()
    )
    return response.data or []


def get_llamadas_periodo(restaurante_id: str, desde_iso: str) -> list[dict]:
    client = get_client()
    response = (
        client.table("llamadas")
        .select("created_at, duracion_segundos, resultado")
        .eq("restaurante_id", restaurante_id)
        .gte("created_at", desde_iso)
        .execute()
    )
    return response.data or []


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
