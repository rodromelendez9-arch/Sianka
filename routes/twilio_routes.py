import asyncio
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
from prompts.agent_prompt import tiempo_entrega, tiempo_recoleccion
from services.cifrado_service import enmascarar_telefono, normalizar_telefono
from services.claude_service import ClaudeConversationService
from services.deepgram_service import DeepgramStreamingService, sintetizar_audio_mulaw
from services.ilustraciones import url_ilustracion
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


LARGO_MINIMO_DIRECCION = 8


def _pesos(valor: float) -> str:
    return f"${valor:.2f}"


def preparar_orden(
    propuesta: dict, menu: list[dict], restaurante: dict, telefono_llamada: Optional[str]
) -> tuple[Optional[dict], str]:
    """Valida lo que Claude propone registrar y calcula el total real.
    Devuelve (orden_lista_para_guardar, mensaje) o (None, motivo_del_rechazo).
    El mensaje vuelve a Claude como resultado de la herramienta, asi que esta
    escrito para que el agente sepa exactamente que decirle al cliente."""
    items_validados, subtotal = _validar_y_recalcular_orden(propuesta.get("items") or [], menu)
    fuera_de_menu = [
        str(i.get("platillo")) for i in propuesta.get("items") or []
        if i.get("platillo") not in {v["platillo"] for v in items_validados}
    ]
    if not items_validados or fuera_de_menu:
        return None, (
            "No se registro: estos platillos no existen en el menu o tienen cantidad invalida: "
            f"{', '.join(fuera_de_menu) or 'ninguno valido'}. Confirma con el cliente usando los nombres exactos del menu."
        )

    nombre = " ".join(str(propuesta.get("nombre_cliente") or "").split())[:LARGO_MAXIMO_NOMBRE]
    if not nombre:
        return None, "No se registro: falta el nombre del cliente para la orden."

    orden: dict = {"items": items_validados, "nombre_cliente": nombre, "tipo_entrega": "recoger", "costo_envio": 0.0}

    if propuesta.get("tipo_entrega") != "domicilio":
        orden["total"] = subtotal
        orden["tiempo_recoleccion"] = tiempo_recoleccion(restaurante)
        return orden, (
            f"Orden registrada para recoger. Total a pagar: {_pesos(subtotal)}. "
            f"Lista en {orden['tiempo_recoleccion']}."
        )

    if not restaurante.get("ofrece_entregas"):
        return None, "No se registro: el restaurante no hace envios a domicilio, solo pedidos para recoger."

    direccion = " ".join(str(propuesta.get("direccion_entrega") or "").split())[:300]
    if len(direccion) < LARGO_MINIMO_DIRECCION:
        return None, "No se registro: falta la direccion completa (calle, numero y colonia)."

    minimo = float(restaurante.get("pedido_minimo_envio") or 0)
    if subtotal < minimo:
        return None, (
            f"No se registro: el pedido minimo para envio es {_pesos(minimo)} y el pedido va en "
            f"{_pesos(subtotal)}. Ofrece agregar algo o pasar a recoger."
        )

    telefono = normalizar_telefono(propuesta.get("telefono_contacto")) or normalizar_telefono(telefono_llamada)
    if not telefono:
        return None, "No se registro: falta un telefono de contacto para el repartidor."

    metodo_pago = propuesta.get("metodo_pago")
    if metodo_pago not in ("efectivo", "tarjeta"):
        return None, "No se registro: falta preguntar si paga en efectivo o con tarjeta al recibir."

    envio = round(float(restaurante.get("costo_envio") or 0), 2)
    total = round(subtotal + envio, 2)

    paga_con = None
    if metodo_pago == "efectivo" and propuesta.get("paga_con"):
        paga_con = round(float(propuesta["paga_con"]), 2)
        if paga_con < total:
            return None, (
                f"No se registro: el cliente dijo que paga con {_pesos(paga_con)}, pero el total con envio "
                f"es {_pesos(total)}. Confirma con cuanto paga."
            )

    orden.update(
        tipo_entrega="domicilio",
        direccion_entrega=direccion,
        referencias_entrega=" ".join(str(propuesta.get("referencias_entrega") or "").split())[:300] or None,
        telefono_contacto=telefono,
        metodo_pago=metodo_pago,
        paga_con=paga_con,
        costo_envio=envio,
        total=total,
        tiempo_recoleccion=tiempo_entrega(restaurante),
    )
    cambio = f" Llevar cambio de {_pesos(paga_con - total)}." if paga_con and paga_con > total else ""
    return orden, (
        f"Orden registrada a domicilio. Total a pagar: {_pesos(total)} (incluye envio de {_pesos(envio)}), "
        f"en {metodo_pago}.{cambio} Entrega estimada en {orden['tiempo_recoleccion']}."
    )


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

    # El numero de Twilio al que marco el cliente identifica al restaurante:
    # cada restaurante tiene el suyo (columna twilio_number, se asigna con
    # admin.py). No hay "restaurante por defecto": con varios restaurantes,
    # una llamada a un numero desconocido contestada por otro negocio seria
    # peor que no contestarla.
    restaurante = (
        supabase_client.get_restaurante_by_twilio_number(numero_llamado) if numero_llamado else None
    )
    if not restaurante:
        logger.error(
            "Llamada a %s sin restaurante asignado. Asignalo con: "
            "python admin.py editar-restaurante <slug> --twilio %s",
            numero_llamado,
            numero_llamado,
        )

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


# Con 2+ palabras el cliente claramente esta hablando encima del agente (y no
# es un "aja" suelto o ruido de linea), asi que se corta el audio en curso.
PALABRAS_PARA_INTERRUMPIR = 2

# Tope al nombre que dicta el cliente: es un nombre de pila, no un campo libre.
LARGO_MAXIMO_NOMBRE = 60

# Al colgar, cuanto se espera a que termine el turno en curso (p. ej. el
# cliente dijo "si, esta bien" y colgo antes de que Claude registrara la orden).
ESPERA_ULTIMO_TURNO_SEGUNDOS = 15


async def _enviar_audio_a_twilio(websocket: WebSocket, stream_sid: Optional[str], audio: bytes) -> bool:
    """Envia el audio seguido de un `mark`: Twilio devuelve ese mark cuando
    termina de reproducirlo, y asi se sabe si el agente sigue hablando."""
    if not stream_sid or not audio:
        return False

    payload = base64.b64encode(audio).decode("utf-8")
    await websocket.send_text(
        json.dumps({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
    )
    await websocket.send_text(
        json.dumps({"event": "mark", "streamSid": stream_sid, "mark": {"name": "fin_respuesta"}})
    )
    return True


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
    nombre_cliente: Optional[str] = None
    llamada_terminada = False

    restaurante: dict = {}
    claude_service: Optional[ClaudeConversationService] = None
    deepgram_service: Optional[DeepgramStreamingService] = None
    menu: list[dict] = []

    # Manejo de turnos: los segmentos is_final se juntan hasta que Deepgram
    # indica que el cliente termino de hablar (speech_final / UtteranceEnd);
    # entonces el turno completo entra a la cola. Un solo worker consume la
    # cola, asi nunca hay dos llamadas a Claude en paralelo sobre el mismo
    # historial ni respuestas a frases a medias.
    segmentos_turno: list[str] = []
    cola_turnos: asyncio.Queue[Optional[str]] = asyncio.Queue()
    worker_turnos: Optional[asyncio.Task] = None
    # Audios enviados a Twilio cuyo mark aun no regresa (= el agente habla).
    marks_pendientes = 0

    async def hablar(texto: str) -> None:
        nonlocal marks_pendientes

        transcripcion_completa.append(f"Agente: {texto}")
        await manager.broadcast(
            restaurante_id,
            {
                "evento": "transcripcion",
                "texto": texto,
                "es_final": True,
                "hablante": "agente",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        if llamada_terminada:
            return

        audio = await sintetizar_audio_mulaw(texto, restaurante.get("voz_tts"))
        if await _enviar_audio_a_twilio(websocket, stream_sid, audio):
            marks_pendientes += 1

    async def interrumpir_agente() -> None:
        """Barge-in: vacia el buffer de audio de Twilio para que el agente se
        calle en cuanto el cliente le habla encima."""
        nonlocal marks_pendientes
        if marks_pendientes <= 0 or not stream_sid or llamada_terminada:
            return
        marks_pendientes = 0
        await websocket.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))

    def cerrar_turno() -> bool:
        """Pasa lo acumulado del cliente a la cola. Sincrono a proposito: los
        callbacks de Deepgram corren como tareas separadas y asi el estado de
        `segmentos_turno` nunca queda repartido entre dos `await`."""
        if not segmentos_turno:
            return False
        cola_turnos.put_nowait(" ".join(segmentos_turno))
        segmentos_turno.clear()
        return True

    async def on_transcript(texto: str, is_final: bool, speech_final: bool) -> None:
        texto = texto.strip()

        if is_final and texto:
            segmentos_turno.append(texto)
        turno_cerrado = cerrar_turno() if speech_final else False

        if texto and (turno_cerrado or len(texto.split()) >= PALABRAS_PARA_INTERRUMPIR):
            await interrumpir_agente()

        if texto:
            await manager.broadcast(
                restaurante_id,
                {
                    "evento": "transcripcion",
                    "texto": texto,
                    "es_final": is_final,
                    "hablante": "cliente",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

    async def on_utterance_end() -> None:
        if cerrar_turno():
            await interrumpir_agente()

    async def registrar_orden(propuesta: dict) -> tuple[bool, str]:
        """Lo llama ClaudeConversationService cuando Claude usa la herramienta.
        La orden se guarda ANTES de hablar: si el cliente cuelga justo despues
        de confirmar, el envio de audio falla pero la orden ya quedo guardada."""
        nonlocal orden_tomada, nombre_cliente

        if not restaurante_id:
            return False, "No se registro: error interno del sistema. Pide disculpas y pide que llame de nuevo."

        orden, mensaje = preparar_orden(propuesta, menu, restaurante, telefono_cliente)
        if orden is None:
            logger.info("Orden rechazada por validacion (llamada_id=%s)", llamada_id)
            return False, mensaje

        nueva_orden = supabase_client.crear_orden(restaurante_id=restaurante_id, llamada_id=llamada_id, **orden)
        orden_tomada = True
        nombre_cliente = orden["nombre_cliente"]

        # Lo asigna la base (trigger trg_ordenes_numero_dia). Se le da a
        # Claude para que se lo diga al cliente: con el pide en el mostrador.
        numero_dia = nueva_orden.get("numero_dia")
        if numero_dia:
            mensaje += f" Numero de orden: {numero_dia}."

        await manager.broadcast(
            restaurante_id,
            {
                "evento": "orden_nueva",
                "orden_id": nueva_orden["id"],
                "numero_dia": numero_dia,
                # La ilustracion viaja con cada platillo para que el panel no
                # duplique en JS la regla de services/ilustraciones.py.
                "items": [{**i, "ilustracion": url_ilustracion(i["platillo"])} for i in orden["items"]],
                "total": orden["total"],
                "recoleccion": orden["tiempo_recoleccion"],
                "nombre_cliente": orden["nombre_cliente"],
                "tipo_entrega": orden["tipo_entrega"],
                "direccion_entrega": orden.get("direccion_entrega"),
                "referencias_entrega": orden.get("referencias_entrega"),
                # Completo solo a domicilio: el repartidor necesita llamar.
                "telefono_contacto": orden.get("telefono_contacto"),
                "metodo_pago": orden.get("metodo_pago"),
                "paga_con": orden.get("paga_con"),
                "costo_envio": orden["costo_envio"],
                "status": "nueva",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True, mensaje

    async def procesar_turno(texto: str) -> None:
        transcripcion_completa.append(f"Cliente: {texto}")

        try:
            resultado = await claude_service.responder(texto, registrar_orden)
            if resultado["texto"]:
                await hablar(resultado["texto"])
        except Exception:
            logger.exception(
                "Error procesando turno de conversacion (llamada_id=%s)",
                llamada_id,
            )
            try:
                await hablar("Disculpa, ¿puedes repetir eso?")
            except Exception:
                logger.exception(
                    "Tambien fallo el TTS de fallback tras un error (llamada_id=%s)",
                    llamada_id,
                )

    async def procesar_turnos() -> None:
        try:
            await hablar(claude_service.saludo)
        except Exception:
            logger.exception("No se pudo reproducir el saludo (llamada_id=%s)", llamada_id)

        while True:
            texto = await cola_turnos.get()
            if texto is None:
                return

            # Si el cliente dijo varias cosas mientras Claude pensaba, se
            # responden juntas en un solo turno en vez de una por una.
            fin = False
            while not cola_turnos.empty():
                siguiente = cola_turnos.get_nowait()
                if siguiente is None:
                    fin = True
                    break
                texto = f"{texto} {siguiente}"

            await procesar_turno(texto)
            if fin:
                return

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

                # El restaurante viene del token firmado que genero el webhook
                # a partir del numero marcado: nombre, menu, saludo y voz de
                # ESTA llamada son los de ese restaurante.
                restaurante = supabase_client.get_restaurante(restaurante_id) or {}
                menu = supabase_client.get_menu_disponible(restaurante_id)
                llamada = supabase_client.crear_llamada(restaurante_id, telefono_cliente)
                llamada_id = llamada["id"]

                claude_service = ClaudeConversationService(
                    restaurante, menu, numero_visible=bool(normalizar_telefono(telefono_cliente))
                )
                deepgram_service = DeepgramStreamingService(
                    on_transcript=on_transcript,
                    on_utterance_end=on_utterance_end,
                )
                await deepgram_service.start()

                await manager.broadcast(
                    restaurante_id,
                    {
                        "evento": "llamada_activa",
                        "telefono_cliente": enmascarar_telefono(telefono_cliente),
                        "llamada_id": llamada_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

                # El worker arranca con el saludo, asi el cliente escucha al
                # agente en cuanto se conecta, sin tener que decir "¿bueno?".
                worker_turnos = asyncio.create_task(procesar_turnos())

            elif evento == "media":
                if deepgram_service:
                    payload_b64 = mensaje["media"]["payload"]
                    audio_chunk = base64.b64decode(payload_b64)
                    await deepgram_service.send_audio(audio_chunk)

            elif evento == "mark":
                marks_pendientes = max(0, marks_pendientes - 1)

            elif evento == "stop":
                break

    except WebSocketDisconnect:
        pass
    finally:
        llamada_terminada = True

        if deepgram_service:
            await deepgram_service.finish()

        # Lo ultimo que dijo el cliente todavia se procesa (sin audio): puede
        # ser la confirmacion de su orden justo antes de colgar.
        if worker_turnos:
            cerrar_turno()
            cola_turnos.put_nowait(None)
            try:
                await asyncio.wait_for(worker_turnos, timeout=ESPERA_ULTIMO_TURNO_SEGUNDOS)
            except asyncio.TimeoutError:
                logger.warning("El ultimo turno no termino a tiempo (llamada_id=%s)", llamada_id)
            except Exception:
                logger.exception("Error en el worker de turnos (llamada_id=%s)", llamada_id)

        duracion = int(time.time() - inicio_llamada)
        if llamada_id:
            supabase_client.actualizar_llamada(
                llamada_id,
                duracion_segundos=duracion,
                transcripcion="\n".join(transcripcion_completa),
                resultado="orden" if orden_tomada else "sin_orden",
                nombre_cliente=nombre_cliente,
            )

        await manager.broadcast(
            restaurante_id,
            {
                "evento": "llamada_terminada",
                "llamada_id": llamada_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
