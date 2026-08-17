import os
from typing import Any, Optional

import anthropic

from prompts.agent_prompt import build_system_prompt

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5"

REGISTRAR_ORDEN_TOOL = {
    "name": "registrar_orden",
    "description": (
        "Registra la orden final del cliente una vez que fue repetida en voz alta "
        "y el cliente confirmo que es correcta. Solo llamar esta herramienta cuando "
        "el cliente haya confirmado explicitamente toda la orden, con todos sus "
        "platillos, cantidades y el total."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "platillo": {"type": "string"},
                        "cantidad": {"type": "integer"},
                        "precio": {"type": "number"},
                        "subtotal": {"type": "number"},
                    },
                    "required": ["platillo", "cantidad", "precio", "subtotal"],
                },
            },
            "total": {"type": "number"},
            "tiempo_recoleccion": {"type": "string"},
        },
        "required": ["items", "total", "tiempo_recoleccion"],
    },
}


class ClaudeConversationService:
    """Mantiene el historial de una llamada y conversa con Claude (Haiku 4.5) turno a turno."""

    def __init__(self, restaurante: dict[str, Any], menu: list[dict[str, Any]]) -> None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY no esta configurado en .env")

        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.system_prompt = build_system_prompt(restaurante, menu)
        self.historial: list[dict[str, Any]] = []

    async def responder(self, texto_usuario: str) -> dict[str, Any]:
        self.historial.append({"role": "user", "content": texto_usuario})

        response = await self.client.messages.create(
            model=MODEL,
            max_tokens=500,
            temperature=0.3,
            system=self.system_prompt,
            messages=self.historial,
            tools=[REGISTRAR_ORDEN_TOOL],
        )

        texto_respuesta = ""
        orden_confirmada: Optional[dict[str, Any]] = None
        tool_use_id: Optional[str] = None
        contenido_para_historial: list[dict[str, Any]] = []

        for bloque in response.content:
            if bloque.type == "text":
                texto_respuesta += bloque.text
                contenido_para_historial.append({"type": "text", "text": bloque.text})
            elif bloque.type == "tool_use" and bloque.name == "registrar_orden":
                orden_confirmada = bloque.input
                tool_use_id = bloque.id
                contenido_para_historial.append(
                    {"type": "tool_use", "id": bloque.id, "name": bloque.name, "input": bloque.input}
                )

        self.historial.append({"role": "assistant", "content": contenido_para_historial})

        if orden_confirmada is not None and tool_use_id is not None:
            self.historial.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": "Orden registrada correctamente en el sistema.",
                        }
                    ],
                }
            )

        return {
            "texto": texto_respuesta,
            "orden": orden_confirmada,
        }
