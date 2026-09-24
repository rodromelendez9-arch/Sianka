import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Conexiones del dashboard agrupadas por restaurante: un evento (llamada
    en vivo, orden nueva) solo llega a los dashboards de SU restaurante --
    nunca se transmite la transcripcion de un cliente a otro negocio."""

    def __init__(self) -> None:
        self.conexiones: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, restaurante_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.conexiones[restaurante_id].append(websocket)

    def disconnect(self, restaurante_id: str, websocket: WebSocket) -> None:
        conexiones = self.conexiones.get(restaurante_id)
        if not conexiones:
            return
        if websocket in conexiones:
            conexiones.remove(websocket)
        if not conexiones:
            del self.conexiones[restaurante_id]

    async def broadcast(self, restaurante_id: str, evento: dict[str, Any]) -> None:
        payload = json.dumps(evento, default=str)
        conexiones_muertas: list[WebSocket] = []

        for connection in list(self.conexiones.get(restaurante_id, [])):
            try:
                await connection.send_text(payload)
            except Exception:
                logger.warning("Conexion WS muerta detectada, se removera del pool")
                conexiones_muertas.append(connection)

        for connection in conexiones_muertas:
            self.disconnect(restaurante_id, connection)


manager = ConnectionManager()
