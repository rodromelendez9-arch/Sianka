import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from database import supabase_client
from services.claude_service import ClaudeConversationService
from services.deepgram_service import DeepgramStreamingService, sintetizar_audio_mulaw
from services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/twilio/incoming")
async def incoming_call(request: Request) -> Response:
    form = await request.form()
    telefono_cliente = str(form.get("From", "desconocido"))

    restaurante = supabase_client.get_restaurante_activo()
    response = VoiceResponse()

    if not restaurante:
        response.say(
            "Lo sentimos, el restaurante no esta disponible en este momento.",
            language="es-MX",
        )
        return Response(content=str(response), media_type="application/xml")

    host = request.url.hostname
    stream_url = f"wss://{host}/media-stream"

    connect = Connect()
    stream = Stream(url=stream_url)
    stream.parameter(name="telefono_cliente", value=telefono_cliente)
    stream.parameter(name="restaurante_id", value=str(restaurante["id"]))
    connect.append(stream)
    response.append(connect)

    return Response(content=str(response), media_type="application/xml")


async def _enviar_audio_a_twilio(websocket: WebSocket, stream_sid: Optional[str], audio: bytes) -> None:
    if not stream_sid or not audio:
        return

    payload = base64.b64encode(audio).decode("utf-8")
    mensaje = {
        "event": "media",
        "streamSid": stream_sid,
        "media": {"payload": payload},
    }
    await websocket.send_text(json.dumps(mensaje))


@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    stream_sid: Optional[str] = None
    telefono_cliente = "desconocido"
    restaurante_id: Optional[str] = None
    llamada_id: Optional[str] = None
    inicio_llamada = time.time()
    transcripcion_completa: list[str] = []
    orden_tomada = False

    claude_service: Optional[ClaudeConversationService] = None
    deepgram_service: Optional[DeepgramStreamingService] = None

    async def on_transcript(texto: str, is_final: bool) -> None:
        nonlocal orden_tomada

        await manager.broadcast(
            {
                "evento": "transcripcion",
                "texto": texto,
                "es_final": is_final,
                "hablante": "cliente",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        if not is_final or not texto.strip() or claude_service is None:
            return

        transcripcion_completa.append(f"Cliente: {texto}")

        try:
            resultado = await claude_service.responder(texto)
            respuesta_texto = resultado["texto"]

            if respuesta_texto:
                transcripcion_completa.append(f"Agente: {respuesta_texto}")
                await manager.broadcast(
                    {
                        "evento": "transcripcion",
                        "texto": respuesta_texto,
                        "es_final": True,
                        "hablante": "agente",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                audio = await sintetizar_audio_mulaw(respuesta_texto)
                await _enviar_audio_a_twilio(websocket, stream_sid, audio)

            orden = resultado["orden"]
            if orden and restaurante_id:
                orden_tomada = True
                items = orden["items"]
                total = orden["total"]
                tiempo_recoleccion = orden.get("tiempo_recoleccion", "20 minutos")

                nueva_orden = supabase_client.crear_orden(
                    restaurante_id=restaurante_id,
                    llamada_id=llamada_id,
                    items=items,
                    total=total,
                    tiempo_recoleccion=tiempo_recoleccion,
                )

                await manager.broadcast(
                    {
                        "evento": "orden_nueva",
                        "orden_id": nueva_orden["id"],
                        "items": items,
                        "total": total,
                        "recoleccion": tiempo_recoleccion,
                        "status": "nueva",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
        except Exception:
            logger.exception(
                "Error procesando turno de conversacion (llamada_id=%s, texto=%r)",
                llamada_id,
                texto,
            )
            try:
                audio_fallback = await sintetizar_audio_mulaw("Disculpa, ¿puedes repetir eso?")
                await _enviar_audio_a_twilio(websocket, stream_sid, audio_fallback)
            except Exception:
                logger.exception(
                    "Tambien fallo el TTS de fallback tras un error (llamada_id=%s)",
                    llamada_id,
                )

    try:
        while True:
            mensaje_raw = await websocket.receive_text()
            mensaje = json.loads(mensaje_raw)
            evento = mensaje.get("event")

            if evento == "start":
                start_data = mensaje["start"]
                stream_sid = start_data["streamSid"]
                custom_params = start_data.get("customParameters", {})
                telefono_cliente = custom_params.get("telefono_cliente", "desconocido")
                restaurante_id = custom_params.get("restaurante_id")

                restaurante = supabase_client.get_restaurante_activo()
                if restaurante and not restaurante_id:
                    restaurante_id = str(restaurante["id"])
                menu = supabase_client.get_menu(restaurante_id) if restaurante_id else []

                if restaurante_id:
                    llamada = supabase_client.crear_llamada(restaurante_id, telefono_cliente)
                    llamada_id = llamada["id"]
                else:
                    logger.warning(
                        "No se pudo determinar restaurante_id al iniciar la llamada; "
                        "no se creara registro de llamada ni de orden"
                    )

                claude_service = ClaudeConversationService(restaurante or {}, menu)
                deepgram_service = DeepgramStreamingService(on_transcript=on_transcript)
                await deepgram_service.start()

                await manager.broadcast(
                    {
                        "evento": "llamada_activa",
                        "telefono_cliente": telefono_cliente,
                        "llamada_id": llamada_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

            elif evento == "media":
                if deepgram_service:
                    payload_b64 = mensaje["media"]["payload"]
                    audio_chunk = base64.b64decode(payload_b64)
                    await deepgram_service.send_audio(audio_chunk)

            elif evento == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        if deepgram_service:
            await deepgram_service.finish()

        duracion = int(time.time() - inicio_llamada)
        if llamada_id:
            supabase_client.actualizar_llamada(
                llamada_id,
                duracion_segundos=duracion,
                transcripcion="\n".join(transcripcion_completa),
                resultado="orden" if orden_tomada else "sin_orden",
            )

        await manager.broadcast(
            {
                "evento": "llamada_terminada",
                "llamada_id": llamada_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
