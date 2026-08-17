from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class Restaurante(BaseModel):
    id: UUID
    nombre: str
    ciudad: Optional[str] = None
    horario: Optional[str] = None
    twilio_number: Optional[str] = None
    activo: bool = True
    created_at: datetime


class PlatilloMenu(BaseModel):
    id: UUID
    restaurante_id: UUID
    platillo: str
    precio: float
    ingredientes: Optional[str] = None
    activo: bool = True


class PlatilloCreate(BaseModel):
    platillo: str
    precio: float
    ingredientes: Optional[str] = None


class PlatilloUpdate(BaseModel):
    platillo: Optional[str] = None
    precio: Optional[float] = None
    ingredientes: Optional[str] = None
    activo: Optional[bool] = None
