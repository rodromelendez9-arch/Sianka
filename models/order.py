from enum import Enum

from pydantic import BaseModel


class OrdenStatus(str, Enum):
    NUEVA = "nueva"
    CONFIRMADA = "confirmada"
    PREPARANDO = "preparando"
    LISTA = "lista"
    ENTREGADA = "entregada"


class OrdenStatusUpdate(BaseModel):
    """Cuerpo de POST /api/ordenes/{id}/status (botones del panel)."""

    status: OrdenStatus
