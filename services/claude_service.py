import os
from typing import Any, Awaitable, Callable

import anthropic

from prompts.agent_prompt import build_saludo, build_system_prompt

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-haiku-4-5"

REGISTRAR_ORDEN_TOOL = {
    "name": "registrar_orden",
    "description": (
        "Registra la orden final del cliente una vez que fue repetida en voz alta "
        "y el cliente confirmo que es correcta. Solo llamar esta herramienta cuando "
        "el cliente haya confirmado explicitamente toda la orden. El sistema valida "
        "la orden y devuelve el total final a cobrar (con envio, si aplica) o el "
        "motivo por el que no se pudo registrar."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "nombre_cliente": {
                "type": "string",
                "description": "Nombre de pila con el que el cliente pidio la orden, tal como lo dijo.",
            },
            "tipo_entrega": {
                "type": "string",
                "enum": ["recoger", "domicilio"],
                "description": "Si el cliente pasa a recoger o se le envia a domicilio.",
            },
            "direccion_entrega": {
                "type": "string",
                "description": "Solo a domicilio: calle, numero, colonia y, si lo dio, codigo postal.",
            },
            "referencias_entrega": {
                "type": "string",
                "description": "Solo a domicilio: entre que calles, color de fachada u otras referencias.",
            },
            "telefono_contacto": {
                "type": "string",
                "description": "Solo si el cliente dio un numero de contacto distinto al de la llamada.",
            },
            "metodo_pago": {
                "type": "string",
                "enum": ["efectivo", "tarjeta"],
                "description": "Solo a domicilio: como pagara al recibir.",
            },
            "paga_con": {
                "type": "number",
                "description": "Solo a domicilio en efectivo: con cuanto va a pagar, para llevar cambio.",
            },
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
        },
        "required": ["nombre_cliente", "tipo_entrega", "items", "total"],
    },
}

# Recibe el input de la herramienta y devuelve (registrada, mensaje para Claude).
RegistrarOrden = Callable[[dict[str, Any]], Awaitable[tuple[bool, str]]]


class ClaudeConversationService:
    """Mantiene el historial de una llamada y conversa con Claude (Haiku 4.5) turno a turno."""

    def __init__(
        self,
        restaurante: dict[str, Any],
        menu: list[dict[str, Any]],
        numero_visible: bool = True,
    ) -> None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY no esta configurado en .env")

        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.system_prompt = build_system_prompt(restaurante, menu, numero_visible=numero_visible)
        self.saludo = build_saludo(restaurante)
        # El historial debe empezar con un turno "user", asi que la entrada de
        # la llamada se representa como un mensaje de sistema entre corchetes
        # y el saludo fijo queda como la primera respuesta del agente. Asi
        # Claude sabe que ya saludo y no lo repite.
        self.historial: list[dict[str, Any]] = [
            {"role": "user", "content": "[Entra la llamada. El cliente aun no ha dicho nada.]"},
            {"role": "assistant", "content": self.saludo},
        ]

    async def _crear(self, **extra: Any) -> Any:
        return await self.client.messages.create(
            model=MODEL,
            max_tokens=500,
            temperature=0.3,
            system=self.system_prompt,
            messages=self.historial,
            tools=[REGISTRAR_ORDEN_TOOL],
            **extra,
        )

    async def responder(self, texto_usuario: str, registrar_orden: RegistrarOrden) -> dict[str, Any]:
        """Un turno de la conversacion. Si Claude llama `registrar_orden`, se
        ejecuta `registrar_orden(input)` y su resultado REAL (registrada o el
        motivo del rechazo) vuelve a Claude, que entonces confirma o corrige
        con el cliente. Asi el agente nunca dice "listo" a una orden que el
        sistema rechazo (fuera de menu, bajo el minimo de envio, etc.)."""
        self.historial.append({"role": "user", "content": texto_usuario})
        response = await self._crear()

        texto_respuesta = ""
        orden_propuesta = None
        tool_use_id = None
        contenido_para_historial: list[dict[str, Any]] = []

        for bloque in response.content:
            if bloque.type == "text":
                texto_respuesta += bloque.text
                contenido_para_historial.append({"type": "text", "text": bloque.text})
            elif bloque.type == "tool_use" and bloque.name == "registrar_orden":
                orden_propuesta = bloque.input
                tool_use_id = bloque.id
                contenido_para_historial.append(
                    {"type": "tool_use", "id": bloque.id, "name": bloque.name, "input": bloque.input}
                )

        self.historial.append({"role": "assistant", "content": contenido_para_historial})

        registrada = False
        if orden_propuesta is not None and tool_use_id is not None:
            registrada, mensaje = await registrar_orden(orden_propuesta)
            self.historial.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": mensaje,
                            "is_error": not registrada,
                        }
                    ],
                }
            )

            # Tras el resultado se pide la respuesta hablada: confirmacion con
            # el total real, o la explicacion de que falta/que corregir. Si la
            # orden se rechazo, lo que Claude haya dicho antes del resultado
            # (p. ej. "listo") se descarta para no confirmar algo falso.
            if not registrada or not texto_respuesta.strip():
                cierre = await self._crear(tool_choice={"type": "none"})
                texto_respuesta = "".join(b.text for b in cierre.content if b.type == "text")
                if texto_respuesta:
                    self.historial.append({"role": "assistant", "content": texto_respuesta})

        return {"texto": texto_respuesta, "orden_registrada": registrada}
