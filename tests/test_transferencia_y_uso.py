"""Fase 1: pasar la llamada a una persona, uso/costo por llamada y la guia
de desvio en la configuracion."""
import asyncio
import json
from types import SimpleNamespace
from unittest import mock

import admin
from prompts.agent_prompt import build_system_prompt
from routes import twilio_routes as tr
from services import claude_service, costos_service, transferencia_service
from services.cifrado_service import telefono_mexico
from tests import fakes
from tests.base import CasoBase


class ClaudeQueTransfiere:
    """Pide transferir cuando el cliente dice "encargado"."""

    restaurante_recibido: dict = {}
    resultado_transferencia = None

    def __init__(self, restaurante, menu, numero_visible=True):
        ClaudeQueTransfiere.restaurante_recibido = restaurante
        self.saludo = "Hola."
        self.uso = {"tokens_entrada": 3000, "tokens_salida": 200}

    async def responder(self, texto, registrar_orden, transferir=None):
        if "encargado" in texto:
            ClaudeQueTransfiere.resultado_transferencia = await transferir("queja")
            return {"texto": "Te comunico con el encargado.", "orden_registrada": False}
        return {"texto": "Claro.", "orden_registrada": False}


class TransferenciaTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.rest = self.restaurante(twilio_number="+529990000001", telefono_transferencia="+529991112222")
        self.transferidas = []

        async def transferir_falso(call_sid, numero):
            self.transferidas.append((call_sid, numero))

        self.parches = [
            mock.patch.object(transferencia_service, "transferir_llamada", transferir_falso),
            mock.patch.object(tr, "ESPERA_DESPEDIDA_SEGUNDOS", 0.3),
        ]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        super().tearDown()

    def _llamada_pidiendo_encargado(self):
        with self.servicios_de_llamada(ClaudeQueTransfiere) as eventos, self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, self.rest)
            self.recibir(ws, 2)
            self.decir(ws, "quiero hablar con el encargado")
            despedida = self.recibir(ws, 2)
            ws.send_text(json.dumps({"event": "mark", "mark": {"name": "fin_respuesta"}}))
            # Twilio corta el stream en cuanto la llamada se transfiere.
            for _ in range(50):
                if self.transferidas:
                    break
                asyncio.run(asyncio.sleep(0.02))
            ws.send_text('{"event": "stop"}')
        return despedida, eventos

    def test_pasa_la_llamada_al_encargado_despues_de_despedirse(self):
        with mock.patch.object(transferencia_service, "disponible", return_value=True):
            despedida, eventos = self._llamada_pidiendo_encargado()

        self.assertIn(("media", "Te comunico con el encargado."), despedida)
        self.assertEqual(self.transferidas, [("CA1", "+529991112222")])
        self.assertTrue(ClaudeQueTransfiere.resultado_transferencia[0])
        llamada = fakes.TABLAS["llamadas"][0]
        self.assertEqual(llamada["resultado"], "transferida")
        self.assertIn("llamada_transferida", [e.get("evento") for e in eventos])

    def test_sin_credenciales_no_se_ofrece_transferir(self):
        with mock.patch.object(transferencia_service, "disponible", return_value=False):
            self._llamada_pidiendo_encargado()

        self.assertIsNone(ClaudeQueTransfiere.restaurante_recibido["telefono_transferencia"])
        self.assertFalse(ClaudeQueTransfiere.resultado_transferencia[0])
        self.assertEqual(self.transferidas, [])
        self.assertEqual(fakes.TABLAS["llamadas"][0]["resultado"], "sin_orden")

    def test_twiml_marca_al_encargado(self):
        twiml = transferencia_service.twiml_transferencia("+529991112222")
        self.assertIn("<Dial", twiml)
        self.assertIn("+529991112222", twiml)


class UsoDeLlamadaTest(CasoBase):
    def test_la_llamada_guarda_uso_y_costo(self):
        rest = self.restaurante(twilio_number="+529990000001")
        with self.servicios_de_llamada(ClaudeQueTransfiere), self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, rest)
            self.recibir(ws, 2)
            self.decir(ws, "una pregunta")
            self.recibir(ws, 2)
            ws.send_text('{"event": "stop"}')

        llamada = fakes.TABLAS["llamadas"][0]
        self.assertEqual(llamada["uso"]["tokens_entrada"], 3000)
        self.assertEqual(llamada["uso"]["caracteres_voz"], len("Hola.") + len("Claro."))
        self.assertGreater(llamada["costo_estimado_usd"], 0)

    def test_estimacion_de_costo(self):
        with mock.patch.dict("os.environ", {
            "COSTO_TELEFONIA_MIN": "0.01", "COSTO_TRANSCRIPCION_MIN": "0.01", "COSTO_VOZ_1K_CARACTERES": "0.03",
            "COSTO_MODELO_1M_ENTRADA": "1", "COSTO_MODELO_1M_SALIDA": "5",
        }):
            costo = costos_service.estimar_costo_usd({
                "duracion_segundos": 61, "caracteres_voz": 1000, "tokens_entrada": 1_000_000, "tokens_salida": 0,
            })
        # 2 minutos iniciados x 0.02 + 0.03 de voz + 1.00 del modelo
        self.assertAlmostEqual(costo, 1.07)

    def test_resumen_por_restaurante(self):
        a = self.restaurante(slug="a", nombre="A")
        b = self.restaurante(slug="b", nombre="B")
        llamadas = [
            {"restaurante_id": a["id"], "duracion_segundos": 120, "resultado": "orden", "costo_estimado_usd": 0.10},
            {"restaurante_id": a["id"], "duracion_segundos": 60, "resultado": "sin_orden", "costo_estimado_usd": 0.05},
            {"restaurante_id": b["id"], "duracion_segundos": 30, "resultado": "orden", "costo_estimado_usd": 0.02},
        ]
        filas = admin.resumen_uso(llamadas, [a, b])
        self.assertEqual([f["slug"] for f in filas], ["a", "b"])
        self.assertEqual((filas[0]["llamadas"], filas[0]["minutos"], filas[0]["pedidos"]), (2, 3.0, 1))
        self.assertAlmostEqual(filas[0]["costo_por_pedido_usd"], 0.15)


class AgenteTest(CasoBase):
    def _servicio(self, **campos):
        rest = {"nombre": "Tacos", **campos}
        return claude_service.ClaudeConversationService(rest, [])

    def test_herramienta_solo_si_hay_telefono(self):
        nombres = lambda s: [t["name"] for t in s.tools]  # noqa: E731
        self.assertEqual(nombres(self._servicio()), ["registrar_orden"])
        self.assertEqual(nombres(self._servicio(telefono_transferencia="+529991112222")),
                         ["registrar_orden", "transferir_llamada"])
        self.assertIn("transferir_llamada", build_system_prompt({"telefono_transferencia": "+52999"}, []))
        self.assertNotIn("transferir_llamada", build_system_prompt({}, []))

    def test_responder_ejecuta_transferir_y_cuenta_tokens(self):
        servicio = self._servicio(telefono_transferencia="+529991112222")
        uso = SimpleNamespace(input_tokens=100, output_tokens=10)
        respuestas = [
            SimpleNamespace(usage=uso, content=[SimpleNamespace(
                type="tool_use", id="t1", name="transferir_llamada", input={"motivo": "queja"})]),
            SimpleNamespace(usage=uso, content=[SimpleNamespace(type="text", text="Te comunico.")]),
        ]
        servicio.client = SimpleNamespace(messages=SimpleNamespace(create=mock.AsyncMock(side_effect=respuestas)))
        motivos = []

        async def transferir(motivo):
            motivos.append(motivo)
            return True, "Transferencia lista."

        resultado = asyncio.run(servicio.responder("quiero al encargado", mock.AsyncMock(), transferir=transferir))
        self.assertEqual(resultado["texto"], "Te comunico.")
        self.assertEqual(motivos, ["queja"])
        self.assertEqual(servicio.uso, {"tokens_entrada": 200, "tokens_salida": 20})


class ConfiguracionLlamadasTest(CasoBase):
    def test_telefono_mexico(self):
        for entrada in ("999 111 2222", "+52 999 111 2222", "52-999-111-2222"):
            self.assertEqual(telefono_mexico(entrada), "+529991112222")
        for entrada in ("12345", "+1 999 111 2222 33", ""):
            self.assertIsNone(telefono_mexico(entrada))

    def test_guardar_telefono_de_transferencia_y_ver_guia(self):
        rest = self.restaurante(twilio_number="+529990000001")
        email, password = self.usuario(rest)
        c = self.cliente()
        self.iniciar_sesion(c, email, password)

        html = c.get("/configuracion").text
        self.assertIn("**61*NUMERO#", html)
        self.assertIn("+529990000001", html)

        r = c.post("/configuracion", data={"nombre": "Tacos", "telefono_transferencia": "999 111 2222"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(rest["telefono_transferencia"], "+529991112222")

        self.assertEqual(c.post("/configuracion", data={"nombre": "Tacos", "telefono_transferencia": "123"}).status_code, 400)
        c.post("/configuracion", data={"nombre": "Tacos", "telefono_transferencia": ""})
        self.assertIsNone(rest["telefono_transferencia"])
