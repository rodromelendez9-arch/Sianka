import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, evento: dict[str, Any]) -> None:
        payload = json.dumps(evento, default=str)
        conexiones_muertas: list[WebSocket] = []

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                logger.warning("Conexion WS muerta detectada, se removera del pool")
                conexiones_muertas.append(connection)

        for connection in conexiones_muertas:
            self.disconnect(connection)


manager = ConnectionManager()
