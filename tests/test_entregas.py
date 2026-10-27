"""Entregas a domicilio, validacion de la orden, registro dentro del turno de
Claude y numero de orden diario."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database import supabase_client as db
from prompts.agent_prompt import build_system_prompt
from routes import twilio_routes as tr
from services import cifrado_service as cs
from services import claude_service
from tests import fakes
from tests.base import TELEFONO_CLIENTE, CasoBase

MENU = [{"platillo": "Taco de cochinita", "precio": 25.0}, {"platillo": "Horchata", "precio": 20.0}]
BASE = {"nombre_cliente": "Ana", "items": [{"platillo": "Taco de cochinita", "cantidad": 4}]}
DOMICILIO = {**BASE, "tipo_entrega": "domicilio", "direccion_entrega": "Calle 59 #512, Centro",
             "referencias_entrega": "Entre 62 y 64, puerta verde", "metodo_pago": "efectivo", "paga_con": 200}


def restaurante_con_envio(**extra) -> dict:
    return {"id": "r1", "slug": "tacos-el-guero", "nombre": "Tacos El Güero", "ofrece_entregas": True,
            "costo_envio": 30, "pedido_minimo_envio": 100, "tiempo_entrega_min": 40,
            "zona_entrega": "Centro y Garcia Gineres", **extra}


class PrepararOrdenTest(CasoBase):
    """La validacion que decide que se guarda y que se le dice al cliente."""

    def setUp(self):
        super().setUp()
        self.rest = restaurante_con_envio()

    def preparar(self, propuesta, rest=None, telefono=TELEFONO_CLIENTE):
        return tr.preparar_orden(propuesta, MENU, rest or self.rest, telefono)

    def test_para_recoger(self):
        orden, msg = self.preparar({**BASE, "tipo_entrega": "recoger"})
        self.assertEqual((orden["total"], orden["costo_envio"]), (100, 0))
        self.assertNotIn("direccion_entrega", orden)
        self.assertIn("recoger", msg)

    def test_a_domicilio(self):
        orden, msg = self.preparar(DOMICILIO)
        self.assertEqual((orden["total"], orden["costo_envio"]), (130, 30))
        self.assertEqual(orden["telefono_contacto"], TELEFONO_CLIENTE)
        for texto in ("$130.00", "cambio de $70.00", "40 minutos"):
            self.assertIn(texto, msg)

    def test_tarjeta_sin_paga_con(self):
        orden, _ = self.preparar({**DOMICILIO, "metodo_pago": "tarjeta", "paga_con": None})
        self.assertEqual(orden["metodo_pago"], "tarjeta")
        self.assertIsNone(orden["paga_con"])

    def test_numero_privado(self):
        orden, msg = self.preparar(DOMICILIO, telefono="Anonymous")
        self.assertIsNone(orden)
        self.assertIn("telefono de contacto", msg)
        orden, _ = self.preparar({**DOMICILIO, "telefono_contacto": "999 111 2233"}, telefono="Anonymous")
        self.assertEqual(orden["telefono_contacto"], "9991112233")

    def test_rechazos_con_motivo_claro(self):
        casos = [
            ("restaurante sin envio", DOMICILIO, restaurante_con_envio(ofrece_entregas=False), "no hace envios"),
            ("bajo el minimo", {**DOMICILIO, "items": [{"platillo": "Taco de cochinita", "cantidad": 2}]}, None, "$100.00"),
            ("direccion incompleta", {**DOMICILIO, "direccion_entrega": "Centro"}, None, "direccion completa"),
            ("sin forma de pago", {**DOMICILIO, "metodo_pago": None}, None, "efectivo o con tarjeta"),
            ("paga con menos", {**DOMICILIO, "paga_con": 100}, None, "$130.00"),
            ("fuera de menu", {**BASE, "tipo_entrega": "recoger",
                               "items": [{"platillo": "Pizza", "cantidad": 1}]}, None, "Pizza"),
            ("sin nombre", {**BASE, "nombre_cliente": "  ", "tipo_entrega": "recoger"}, None, "nombre"),
        ]
        for nombre, propuesta, rest, esperado in casos:
            with self.subTest(nombre):
                orden, msg = self.preparar(propuesta, rest)
                self.assertIsNone(orden)
                self.assertIn(esperado, msg)

    def test_prompt_de_entregas(self):
        prompt = build_system_prompt(self.rest, [])
        for texto in ("$30.00 MXN", "$100.00 MXN", "Centro y Garcia Gineres", "NO se lo pidas"):
            self.assertIn(texto, prompt)
        self.assertIn("numero PRIVADO", build_system_prompt(self.rest, [], numero_visible=False))
        sin_envio = build_system_prompt(restaurante_con_envio(ofrece_entregas=False), [])
        self.assertIn("SOLO maneja pedidos para recoger", sin_envio)


class ClaudeServiceTest(CasoBase):
    """ClaudeConversationService real con un cliente de Anthropic falso."""

    class _Mensajes:
        def __init__(self, respuestas):
            self.respuestas, self.llamadas = list(respuestas), []

        async def create(self, **kw):
            self.llamadas.append({**kw, "messages": json.loads(json.dumps(kw["messages"], default=str))})
            return self.respuestas.pop(0)

    @staticmethod
    def _texto(t):
        return SimpleNamespace(type="text", text=t)

    @staticmethod
    def _herramienta():
        return SimpleNamespace(type="tool_use", name="registrar_orden", id="tu_1", input={})

    def servicio(self, *respuestas):
        svc = claude_service.ClaudeConversationService(restaurante_con_envio(), MENU)
        svc.client = SimpleNamespace(messages=self._Mensajes([SimpleNamespace(content=r) for r in respuestas]))
        return svc

    def test_orden_rechazada_no_se_confirma(self):
        svc = self.servicio([self._texto("¡Listo, ya quedó!"), self._herramienta()],
                            [self._texto("Perdón, el mínimo para envío es de 100 pesos.")])

        async def rechazar(_):
            return False, "No se registro: el pedido minimo para envio es $100.00"

        r = asyncio.run(svc.responder("sí confirmo", rechazar))
        self.assertEqual(r, {"texto": "Perdón, el mínimo para envío es de 100 pesos.", "orden_registrada": False})
        resultado = svc.client.messages.llamadas[1]["messages"][-1]["content"][0]
        self.assertTrue(resultado["is_error"])
        self.assertIn("minimo", resultado["content"])
        self.assertEqual(svc.client.messages.llamadas[1]["tool_choice"], {"type": "none"})

    def test_orden_aceptada_sin_texto_pide_el_cierre(self):
        svc = self.servicio([self._herramienta()], [self._texto("Son 130 pesos, llega en 40 minutos.")])

        async def aceptar(_):
            return True, "Orden registrada. Total a pagar: $130.00"

        r = asyncio.run(svc.responder("sí confirmo", aceptar))
        self.assertTrue(r["orden_registrada"])
        self.assertIn("130", r["texto"])
        self.assertEqual(len(svc.client.messages.llamadas), 2)

    def test_turno_normal_es_una_sola_llamada(self):
        svc = self.servicio([self._texto("¿A domicilio o pasas por él?")])

        async def no_debe_llamarse(_):
            raise AssertionError("no hubo herramienta")

        r = asyncio.run(svc.responder("quiero 4 tacos", no_debe_llamarse))
        self.assertFalse(r["orden_registrada"])
        self.assertEqual(len(svc.client.messages.llamadas), 1)


class ClaudeQuePideADomicilio:
    def __init__(self, restaurante, menu, numero_visible=True):
        self.saludo = "Hola"

    async def responder(self, texto, registrar_orden, transferir=None):
        ok, mensaje = await registrar_orden(DOMICILIO)
        return {"texto": mensaje, "orden_registrada": ok}


class EntregaCompletaTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.rest = self.restaurante(twilio_number="+529990000001", ofrece_entregas=True, costo_envio=30,
                                     pedido_minimo_envio=100, tiempo_entrega_min=40)
        self.platillo(self.rest, "Taco de cochinita", 25)
        self.email, self.password = self.usuario(self.rest)

    def _llamada(self):
        with self.servicios_de_llamada(ClaudeQuePideADomicilio) as eventos, self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, self.rest)
            self.recibir(ws, 2)
            self.decir(ws, "si")
            respuesta = self.recibir(ws, 2)
            ws.send_text('{"event": "stop"}')
        return eventos, respuesta

    def test_pedido_a_domicilio_de_punta_a_punta(self):
        eventos, respuesta = self._llamada()
        orden = fakes.TABLAS["ordenes"][0]
        for campo in ("direccion_entrega", "referencias_entrega", "telefono_contacto"):
            self.assertTrue(cs.esta_cifrado(orden[campo]), campo)
        self.assertEqual((orden["tipo_entrega"], orden["total"], orden["costo_envio"], orden["metodo_pago"]),
                         ("domicilio", 130, 30, "efectivo"))

        nueva = next(e for e in eventos if e["evento"] == "orden_nueva")
        self.assertEqual(nueva["direccion_entrega"], "Calle 59 #512, Centro")
        self.assertEqual(nueva["telefono_contacto"], TELEFONO_CLIENTE, "el repartidor necesita el numero completo")

        # Numero de orden diario: lo asigna la base y el agente se lo dice al cliente
        self.assertEqual(orden["numero_dia"], 1)
        self.assertEqual(nueva["numero_dia"], 1)
        hablado = [texto for tipo, *resto in respuesta if tipo == "media" for texto in resto]
        self.assertTrue(any("Numero de orden: 1." in texto for texto in hablado), hablado)

        c = self.cliente()
        self.iniciar_sesion(c, self.email, self.password)
        panel = c.get("/").text
        for texto in ('data-tipo="domicilio"', "Calle 59 #512, Centro", f'href="tel:{TELEFONO_CLIENTE}"',
                      "cambio $70.00", "Envio", "Entrega: 40 minutos", "<strong>001</strong>"):
            self.assertIn(texto, panel)

    def test_numeracion_y_ordenes_anteriores(self):
        db.crear_orden(self.rest["id"], None, [], 10.0)
        db.crear_orden(self.rest["id"], None, [], 20.0)
        fakes.TABLAS["ordenes"].append({"id": "abcdef1234567890", "restaurante_id": self.rest["id"], "items": [],
                                        "total": 5, "status": "nueva", "created_at": "2026-01-01T00:00:00+00:00"})
        c = self.cliente()
        self.iniciar_sesion(c, self.email, self.password)
        panel = c.get("/").text
        self.assertIn('data-numero="001"', panel)
        self.assertIn('data-numero="002"', panel)
        self.assertIn('data-numero="#abcdef12"', panel, "las ordenes previas a la migracion 005 usan el id")

    def test_configuracion_de_entregas(self):
        c = self.cliente()
        self.iniciar_sesion(c, self.email, self.password)
        r = c.post("/configuracion", data={"nombre": "Tacos El Güero", "costo_envio": "35",
                                           "pedido_minimo_envio": "150", "zona_entrega": "Solo Centro"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(self.rest["ofrece_entregas"], "casilla sin marcar = desactivado")
        self.assertEqual((self.rest["costo_envio"], self.rest["zona_entrega"]), (35, "Solo Centro"))

        c.post("/configuracion", data={"nombre": "Tacos El Güero", "ofrece_entregas": "on", "aviso_en_llamada": "on",
                                       "url_aviso_privacidad_propia": "https://tacoselguero.mx/privacidad"})
        self.assertTrue(self.rest["ofrece_entregas"] and self.rest["aviso_en_llamada"])
        self.assertEqual(self.rest["url_aviso_privacidad"], "https://tacoselguero.mx/privacidad")

        for datos in ({"url_aviso_privacidad_propia": "http://x.mx"}, {"costo_envio": "-5"},
                      {"email_privacidad": "no-es-correo"}):
            with self.subTest(datos):
                self.assertEqual(c.post("/configuracion", data={"nombre": "x", **datos}).status_code, 400)

    def test_retencion_y_arco_borran_datos_de_entrega(self):
        self._llamada()
        orden = fakes.TABLAS["ordenes"][0]
        orden["created_at"] = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        self.assertEqual(db.purgar_datos_entrega(limite), 1)
        self.assertIsNone(orden["direccion_entrega"])
        self.assertIsNone(orden["telefono_contacto"])
        self.assertEqual(orden["total"], 130, "el pedido se conserva")

        orden.update(direccion_entrega=cs.cifrar("Calle 1"), telefono_contacto=cs.cifrar(TELEFONO_CLIENTE))
        db.anonimizar_cliente(self.rest["id"], TELEFONO_CLIENTE)
        self.assertIsNone(orden["direccion_entrega"])
        self.assertIsNone(orden["telefono_contacto"])
