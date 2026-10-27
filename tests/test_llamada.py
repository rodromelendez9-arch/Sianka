"""Manejo de la llamada: saludo, turnos, interrupciones y cierre."""
import asyncio

from services import cifrado_service as cs
from tests import fakes
from tests.base import CasoBase

PEDIDO = {
    "nombre_cliente": "Ana",
    "tipo_entrega": "recoger",
    "items": [{"platillo": "Taco de cochinita", "cantidad": 3, "precio": 1, "subtotal": 3}],
    "total": 3,
}


class ClaudeGuionado:
    """Responde con eco y registra el pedido cuando el cliente dice
    "confirmo". Mide si alguna vez hubo dos turnos en paralelo."""

    recibidos: list[str] = []
    max_en_paralelo = 0

    def __init__(self, restaurante, menu, numero_visible=True):
        from prompts.agent_prompt import build_saludo

        self.saludo = build_saludo(restaurante)
        self.en_curso = 0

    async def responder(self, texto, registrar_orden, transferir=None):
        self.en_curso += 1
        ClaudeGuionado.max_en_paralelo = max(ClaudeGuionado.max_en_paralelo, self.en_curso)
        ClaudeGuionado.recibidos.append(texto)
        await asyncio.sleep(0.2)
        self.en_curso -= 1
        if "confirmo" in texto:
            ok, _ = await registrar_orden(PEDIDO)
            return {"texto": "Listo, en 20 minutos.", "orden_registrada": ok}
        return {"texto": f"Respuesta a: {texto}", "orden_registrada": False}


class LlamadaTest(CasoBase):
    def setUp(self):
        super().setUp()
        ClaudeGuionado.recibidos = []
        ClaudeGuionado.max_en_paralelo = 0
        self.rest = self.restaurante(twilio_number="+529990000001")
        self.platillo(self.rest, "Taco de cochinita", 25)

    def test_llamada_completa(self):
        with self.servicios_de_llamada(ClaudeGuionado), self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, self.rest)
            saludo = self.recibir(ws, 2)

            # Un turno que llega en dos segmentos recibe UNA sola respuesta
            self.decir(ws, "quiero tres tacos", fin_de_turno=False)
            self.decir(ws, "de cochinita por favor")
            turno_1 = self.recibir(ws, 2)

            # El cliente habla encima del agente: se corta el audio
            self.decir(ws, "oye espera", final=False, fin_de_turno=False)
            interrupcion = self.recibir(ws, 2)

            # Turno cerrado por silencio (UtteranceEnd) en vez de speech_final
            self.decir(ws, "si confirmo", fin_de_turno=False)
            self.silencio(ws)
            turno_2 = self.recibir(ws, 2)
            ws.send_text('{"event": "stop"}')

        self.assertEqual(saludo[0], ("media", "¡Hola, gracias por llamar a Tacos El Güero! ¿Qué te preparamos hoy?"))
        self.assertEqual(saludo[1], ("mark",))
        self.assertIn(("media", "Respuesta a: quiero tres tacos de cochinita por favor"), turno_1)
        self.assertIn(("clear",), interrupcion)
        self.assertIn(("media", "Listo, en 20 minutos."), turno_2)
        self.assertEqual(ClaudeGuionado.recibidos, ["quiero tres tacos de cochinita por favor", "si confirmo"])
        self.assertEqual(ClaudeGuionado.max_en_paralelo, 1, "dos turnos de Claude corrieron en paralelo")

        orden = fakes.TABLAS["ordenes"][0]
        self.assertEqual(orden["total"], 75.0, "el precio se recalcula con el menu, no con lo que dice el modelo")
        llamada = fakes.TABLAS["llamadas"][0]
        self.assertEqual(llamada["resultado"], "orden")
        transcripcion = cs.descifrar(llamada["transcripcion"])
        self.assertTrue(transcripcion.startswith("Agente: ¡Hola, gracias por llamar"))
        self.assertIn("Cliente: si confirmo", transcripcion)

    def test_token_invalido_rechaza_el_stream(self):
        with self.servicios_de_llamada(ClaudeGuionado), self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            ws.send_text('{"event": "start", "start": {"streamSid": "X", "customParameters": {"stream_token": "falso"}}}')
            with self.assertRaises(Exception):
                ws.receive_text()
        self.assertEqual(fakes.TABLAS["llamadas"], [])
