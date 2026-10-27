"""Pasar una llamada en curso al telefono del encargado del restaurante.

Se le cambian las instrucciones a la llamada viva: Twilio corta el stream
de audio del agente y marca al encargado. El cliente sigue en la linea; el
encargado ve el numero del cliente como identificador de llamada.
"""
import asyncio
import os

from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

SEGUNDOS_TIMBRANDO = 25


def twiml_transferencia(numero: str) -> str:
    respuesta = VoiceResponse()
    respuesta.dial(numero, timeout=SEGUNDOS_TIMBRANDO)
    # Solo se escucha si el encargado no contesta.
    respuesta.say(
        "En este momento no fue posible comunicarte. Por favor llama de nuevo en unos minutos.",
        language="es-MX",
    )
    return str(respuesta)


def disponible() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN"))


def _transferir(call_sid: str, numero: str) -> None:
    cliente = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    cliente.calls(call_sid).update(twiml=twiml_transferencia(numero))


async def transferir_llamada(call_sid: str, numero: str) -> None:
    await asyncio.to_thread(_transferir, call_sid, numero)
