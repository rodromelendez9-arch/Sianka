"""Aislamiento entre restaurantes: sesion, panel, API, WebSocket y llamadas."""
import asyncio
from unittest import mock

from prompts.agent_prompt import build_saludo, build_system_prompt
from routes import twilio_routes as tr
from services.websocket_manager import manager
from tests import fakes
from tests.base import CasoBase


class MultiRestauranteTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.a = self.restaurante("tacos-el-guero", "Tacos El Güero", twilio_number="+529990000001")
        self.b = self.restaurante("tortas-la-abuela", "Tortas La Abuela", twilio_number="+522220000002",
                                  saludo="Tortas La Abuela, buenas tardes", tiempo_recoleccion_min=35,
                                  instrucciones_extra="Los martes hay 2x1.")
        self.email, self.password = self.usuario(self.a, "guero@x.mx")
        self.torta = self.platillo(self.b, "Torta de pierna", 60)

    def _sesion_de_a(self):
        c = self.cliente()
        self.assertEqual(self.iniciar_sesion(c, self.email, self.password).status_code, 303)
        return c

    # ---------------- Login ----------------

    def test_sin_sesion(self):
        c = self.cliente()
        inicio = c.get("/")
        self.assertEqual(inicio.status_code, 200, "sin sesion, / es la pagina de venta")
        self.assertNotIn("Tacos El Güero", inicio.text, "la pagina de venta no expone datos de restaurantes")
        self.assertEqual(c.get("/panel").headers.get("location"), "/login")
        self.assertEqual(c.get("/api/menu").status_code, 401)

    def test_login(self):
        c = self.cliente()
        self.assertEqual(self.iniciar_sesion(c, self.email, "incorrecta").status_code, 401)
        self.assertEqual(self.iniciar_sesion(c, "%", "x").status_code, 401, "el correo no acepta comodines")
        self.assertEqual(self.iniciar_sesion(c, "GUERO@x.mx", self.password).status_code, 303)
        self.assertIn("Tacos El Güero", c.get("/").text)

    def test_bloqueo_tras_intentos_fallidos(self):
        c = self.cliente()
        for _ in range(5):
            self.iniciar_sesion(c, self.email, "incorrecta")
        self.assertEqual(self.iniciar_sesion(c, self.email, self.password).status_code, 429)

    # ---------------- Datos de otro restaurante ----------------

    def test_no_modifica_platillos_de_otro_restaurante(self):
        c = self._sesion_de_a()
        r = c.post(f"/api/menu/{self.torta['id']}/disponibilidad", json={"disponible": False})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(c.delete(f"/api/menu/{self.torta['id']}").status_code, 404)
        torta = next(m for m in fakes.TABLAS["menus"] if m["id"] == self.torta["id"])
        self.assertTrue(torta["disponible"] and torta["activo"])

    def test_platillo_nuevo_queda_en_su_restaurante(self):
        c = self._sesion_de_a()
        c.post("/api/menu", json={"platillo": "Taco de pastor", "precio": 22})
        del_a = [m["platillo"] for m in fakes.TABLAS["menus"] if m["restaurante_id"] == self.a["id"]]
        self.assertEqual(del_a, ["Taco de pastor"])

    def test_configuracion_solo_cambia_su_restaurante(self):
        c = self._sesion_de_a()
        r = c.post("/configuracion", data={"nombre": "Tacos El Güero Centro", "tiempo_recoleccion_min": "15",
                                           "instrucciones_extra": "Martes 2x1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.a["nombre"], "Tacos El Güero Centro")
        self.assertEqual(self.a["tiempo_recoleccion_min"], 15)
        self.assertEqual(self.b["nombre"], "Tortas La Abuela")
        self.assertEqual(c.post("/configuracion", data={"nombre": "x", "tiempo_recoleccion_min": "0"}).status_code, 400)

    # ---------------- WebSocket ----------------

    def test_panel_solo_recibe_eventos_de_su_restaurante(self):
        c = self._sesion_de_a()
        with c.websocket_connect("/ws/dashboard") as ws:
            asyncio.run(manager.broadcast(self.b["id"], {"evento": "secreto_de_b"}))
            asyncio.run(manager.broadcast(self.a["id"], {"evento": "para_a"}))
            self.assertEqual(ws.receive_json()["evento"], "para_a")

    def test_websocket_sin_sesion_se_rechaza(self):
        with self.assertRaises(Exception):
            with self.cliente().websocket_connect("/ws/dashboard") as ws:
                ws.receive_text()

    # ---------------- Llamadas ----------------

    def test_el_numero_marcado_decide_el_restaurante(self):
        c = self.cliente()
        with mock.patch.object(tr, "_validar_firma_twilio", lambda req, form: True):
            r = c.post("/webhook/twilio/incoming", data={"From": "+5215555", "To": "+522220000002"})
            token = r.text.split('value="')[1].split('"')[0]
            self.assertEqual(tr._validar_stream_token(token)["restaurante_id"], self.b["id"])

            r = c.post("/webhook/twilio/incoming", data={"From": "+5215555", "To": "+520000000000"})
            self.assertIn("no esta disponible", r.text)
            self.assertNotIn("<Stream", r.text, "un numero desconocido no cae en otro restaurante")

    def test_webhook_sin_firma_de_twilio_se_rechaza(self):
        r = self.cliente().post("/webhook/twilio/incoming", data={"From": "+5215555", "To": "+522220000002"})
        self.assertEqual(r.status_code, 403)

    def test_prompt_y_saludo_usan_los_datos_de_cada_restaurante(self):
        self.assertEqual(build_saludo(self.b), "Tortas La Abuela, buenas tardes ¿Qué te preparamos hoy?")
        prompt_b = build_system_prompt(self.b, [self.torta])
        self.assertIn("35 minutos", prompt_b)
        self.assertIn("Los martes hay 2x1.", prompt_b)
        self.assertIn("Torta de pierna", prompt_b)
