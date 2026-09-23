from typing import Optional

from pydantic import BaseModel

# Cuerpos de las peticiones del panel a /api/menu (ver routes/order_routes.py).


class PlatilloCreate(BaseModel):
    platillo: str
    precio: float
    ingredientes: Optional[str] = None


class PlatilloUpdate(BaseModel):
    platillo: Optional[str] = None
    precio: Optional[float] = None
    ingredientes: Optional[str] = None
    activo: Optional[bool] = None
    disponible: Optional[bool] = None


class DisponibilidadUpdate(BaseModel):
    disponible: bool
