from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class OrdenStatus(str, Enum):
    NUEVA = "nueva"
    CONFIRMADA = "confirmada"
    PREPARANDO = "preparando"
    LISTA = "lista"
    ENTREGADA = "entregada"


class LlamadaResultado(str, Enum):
    ORDEN = "orden"
    SIN_ORDEN = "sin_orden"


class ItemOrden(BaseModel):
    platillo: str
    cantidad: int
    precio: float
    subtotal: float


class OrdenCreate(BaseModel):
    restaurante_id: UUID
    llamada_id: Optional[UUID] = None
    items: list[ItemOrden]
    total: float
    tiempo_recoleccion: str = "20 minutos"


class OrdenStatusUpdate(BaseModel):
    status: OrdenStatus


class Orden(BaseModel):
    id: UUID
    restaurante_id: UUID
    llamada_id: Optional[UUID] = None
    items: list[ItemOrden]
    total: float
    tiempo_recoleccion: Optional[str] = None
    status: OrdenStatus = OrdenStatus.NUEVA
    created_at: datetime
    updated_at: datetime


class OrdenEventoWS(BaseModel):
    evento: str = "orden_nueva"
    orden_id: UUID
    items: list[ItemOrden]
    total: float
    recoleccion: str
    status: OrdenStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Llamada(BaseModel):
    id: UUID
    restaurante_id: UUID
    telefono_cliente: Optional[str] = None
    duracion_segundos: Optional[int] = None
    transcripcion: Optional[str] = None
    resultado: Optional[LlamadaResultado] = None
    created_at: datetime
