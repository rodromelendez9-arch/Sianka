import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response, WebSocket, WebSocketDisconnect
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from database import supabase_client
from services.claude_service import ClaudeConversationService
from services.deepgram_service import DeepgramStreamingService, sintetizar_audio_mulaw
from services.rate_limit_service import limitar
from services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# El webhook HTTP valida la firma de Twilio, pero Twilio no firma el handshake
# del WebSocket de Media Streams -- sin esto, cualquiera que adivine la URL
# wss://.../media-stream podria simular una llamada completa (costo de
# Deepgram/Anthropic, ordenes falsas). Por eso el webhook le entrega al
# <Stream> un token firmado y de vida corta, y el WebSocket lo exige antes de
# crear la llamada. Se firma con TWILIO_AUTH_TOKEN porque ya es un secreto
# que el proyecto requiere y que solo el propio backend conoce.
_STREAM_TOKEN_SALT = "media-stream"
_STREAM_TOKEN_MAX_AGE_SEGUNDOS = 60


def _stream_token_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(TWILIO_AUTH_TOKEN, salt=_STREAM_TOKEN_SALT)


def _generar_stream_token(restaurante_id: str, telefono_cliente: str) -> str:
    return _stream_token_serializer().dumps(
        {"restaurante_id": restaurante_id, "telefono_cliente": telefono_cliente}
    )


def _validar_stream_token(token: str) -> Optional[dict]:
    try:
        return _stream_token_serializer().loads(token, max_age=_STREAM_TOKEN_MAX_AGE_SEGUNDOS)
    except (BadSignature, SignatureExpired):
        return None


def _validar_y_recalcular_orden(
    items_propuestos: list[dict], menu: list[dict]
) -> tuple[list[dict], float]:
    """Ignora precio/subtotal/total que propone el modelo y los recalcula con
    el precio real vigente en el menu -- una alucinacion o manipulacion del
    cliente durante la llamada no debe poder registrar una orden con precios
    incorrectos. Cualquier platillo que no exista literalmente en el menu
    activo se descarta en vez de guardarse."""
    precios_reales = {item["platillo"]: float(item["precio"]) for item in menu}

    items_validados: list[dict] = []
    total = 0.0

    for item in items_propuestos:
        platillo = item.get("platillo")
        precio_real = precios_reales.get(platillo)
        cantidad = int(item.get("cantidad") or 0)

        if precio_real is None or cantidad <= 0:
            logger.warning("Item fuera del menu o cantidad invalida, se descarta: %r", item)
            continue

        subtotal = round(precio_real * cantidad, 2)
        items_validados.append(
            {"platillo": platillo, "cantidad": cantidad, "precio": precio_real, "subtotal": subtotal}
        )
        total += subtotal

    return items_validados, round(total, 2)


def _validar_firma_twilio(request: Request, form: dict[str, str]) -> bool:
    """Confirma que la peticion realmente viene de Twilio (y no de alguien
    que descubrio la URL del webhook e intenta inyectar llamadas falsas).
    Reconstruye la URL publica tal como Twilio la vio: usa X-Forwarded-Proto
    y Host porque detras de ngrok/un proxy, request.url.scheme suele
    reportar http aunque Twilio llamo por https."""
    if not TWILIO_AUTH_TOKEN:
        logger.error("TWILIO_AUTH_TOKEN no configurado; se rechaza el webhook por seguridad")
        return False

    firma = request.headers.get("x-twilio-signature", "")
    if not firma:
        return False

    esquema = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    url = f"{esquema}://{host}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(url, form, firma)


@router.post("/webhook/twilio/incoming", dependencies=[Depends(limitar(30, 60))])
async def incoming_call(request: Request) -> Response:
    form = await request.form()
    form_dict = {k: str(v) for k, v in form.items()}

    if not _validar_firma_twilio(request, form_dict):
        logger.warning("Firma de Twilio invalida en /webhook/twilio/incoming; peticion rechazada")
        return Response(status_code=403)

    telefono_cliente = str(form.get("From", "desconocido"))
    numero_llamado = str(form.get("To", ""))

    # Resuelve el restaurante por el numero de Twilio al que realmente
    # marco el cliente -- asi un mismo despliegue puede atender a varios
    # restaurantes, cada uno con su propio numero. Si no hay coincidencia
    # (instalacion de un solo restaurante, o twilio_number aun sin
    # configurar en la fila) cae de vuelta al unico restaurante activo,
    # que es el comportamiento que ya tenia el MVP.
    restaurante = (
        supabase_client.get_restaurante_by_twilio_number(numero_llamado) if numero_llamado else None
    )
    if not restaurante:
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
    stream_token = _generar_stream_token(str(restaurante["id"]), telefono_cliente)

    connect = Connect()
    stream = Stream(url=stream_url)
    stream.parameter(name="stream_token", value=stream_token)
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
    menu: list[dict] = []

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
                items_validados, total_validado = _validar_y_recalcular_orden(orden["items"], menu)
                tiempo_recoleccion = orden.get("tiempo_recoleccion", "20 minutos")

                if not items_validados:
                    logger.warning(
                        "Orden descartada: ningun item coincide con el menu real (llamada_id=%s)",
                        llamada_id,
                    )
                else:
                    orden_tomada = True
                    nueva_orden = supabase_client.crear_orden(
                        restaurante_id=restaurante_id,
                        llamada_id=llamada_id,
                        items=items_validados,
                        total=total_validado,
                        tiempo_recoleccion=tiempo_recoleccion,
                    )

                    await manager.broadcast(
                        {
                            "evento": "orden_nueva",
                            "orden_id": nueva_orden["id"],
                            "items": items_validados,
                            "total": total_validado,
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

                datos_token = _validar_stream_token(custom_params.get("stream_token", ""))
                if not datos_token:
                    logger.warning(
                        "Conexion a /media-stream rechazada: stream_token ausente, invalido o expirado"
                    )
                    await websocket.close(code=1008)
                    return

                telefono_cliente = datos_token["telefono_cliente"]
                restaurante_id = datos_token["restaurante_id"]

                # Se busca por id (no get_restaurante_activo) porque con mas
                # de un restaurante activo simultaneamente, "el activo" ya no
                # identifica de forma unica cual contesto esta llamada.
                restaurante = supabase_client.get_restaurante(restaurante_id)
                menu = supabase_client.get_menu_disponible(restaurante_id)
                llamada = supabase_client.crear_llamada(restaurante_id, telefono_cliente)
                llamada_id = llamada["id"]

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
