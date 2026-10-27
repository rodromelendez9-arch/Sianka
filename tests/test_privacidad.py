"""Datos personales: cifrado en la base, minimizacion en el panel, ARCO,
retencion y paginas publicas."""
from datetime import datetime, timedelta, timezone

from database import supabase_client as db
from prompts.agent_prompt import build_saludo, build_system_prompt
from services import cifrado_service as cs
from tests import fakes
from tests.base import TELEFONO_CLIENTE, CasoBase


class ClaudeQueRegistra:
    def __init__(self, restaurante, menu, numero_visible=True):
        self.saludo = build_saludo(restaurante)

    async def responder(self, texto, registrar_orden, transferir=None):
        ok, mensaje = await registrar_orden({
            "nombre_cliente": "  María   Fernanda ", "tipo_entrega": "recoger",
            "items": [{"platillo": "Taco de cochinita", "cantidad": 2}], "total": 1,
        })
        return {"texto": mensaje, "orden_registrada": ok}


class DatosPersonalesTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.rest = self.restaurante(twilio_number="+529990000001", razon_social="Juan Pérez López",
                                     domicilio="Calle 60, Mérida", email_privacidad="privacidad@tacos.mx")
        self.platillo(self.rest, "Taco de cochinita", 25)
        self.email, self.password = self.usuario(self.rest)

    def _llamada_con_orden(self):
        with self.servicios_de_llamada(ClaudeQueRegistra) as eventos, self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, self.rest)
            self.recibir(ws, 2)
            self.decir(ws, "dos de cochinita")
            self.recibir(ws, 2)
            ws.send_text('{"event": "stop"}')
        return eventos

    def test_la_base_nunca_guarda_datos_personales_en_claro(self):
        self._llamada_con_orden()
        llamada, orden = fakes.TABLAS["llamadas"][0], fakes.TABLAS["ordenes"][0]
        for valor in (llamada["telefono_cliente"], llamada["transcripcion"], llamada["nombre_cliente"],
                      orden["nombre_cliente"]):
            self.assertTrue(cs.esta_cifrado(valor), valor)
        self.assertEqual(cs.descifrar(orden["nombre_cliente"]), "María Fernanda")
        self.assertEqual(llamada["telefono_hash"], cs.huella_telefono(TELEFONO_CLIENTE))

    def test_el_panel_muestra_el_telefono_enmascarado(self):
        eventos = self._llamada_con_orden()
        en_vivo = next(e for e in eventos if e["evento"] == "llamada_activa")
        self.assertEqual(en_vivo["telefono_cliente"], "•••• 4567")

        c = self.cliente()
        self.iniciar_sesion(c, self.email, self.password)
        self.assertIn("María Fernanda", c.get("/").text)
        historial = c.get("/llamadas").text
        self.assertIn("•••• 4567", historial)
        self.assertNotIn("9991234567", historial)
        api = c.get("/api/llamadas").json()[0]
        self.assertEqual(api["telefono_cliente"], "•••• 4567")
        self.assertNotIn("telefono_hash", api)

    def test_cabeceras_de_seguridad(self):
        c = self.cliente()
        self.iniciar_sesion(c, self.email, self.password)
        panel = c.get("/")
        self.assertEqual(panel.headers["cache-control"], "no-store")
        self.assertIn("microphone=()", panel.headers["permissions-policy"])
        self.assertEqual(c.get("/static/js/dashboard.js").headers["cache-control"], "no-cache")

    def test_arco_acceso_y_cancelacion(self):
        self._llamada_con_orden()
        encontradas = db.get_llamadas_por_telefono(self.rest["id"], "+52 999 123 4567")
        self.assertEqual(len(encontradas), 1)
        self.assertEqual(encontradas[0]["telefono_cliente"], TELEFONO_CLIENTE)
        self.assertEqual(encontradas[0]["ordenes"][0]["nombre_cliente"], "María Fernanda")
        self.assertEqual(db.get_llamadas_por_telefono("otro-restaurante", TELEFONO_CLIENTE), [])

        self.assertEqual(db.anonimizar_cliente(self.rest["id"], TELEFONO_CLIENTE), 1)
        llamada, orden = fakes.TABLAS["llamadas"][0], fakes.TABLAS["ordenes"][0]
        for campo in ("telefono_cliente", "telefono_hash", "nombre_cliente", "transcripcion"):
            self.assertIsNone(llamada[campo], campo)
        self.assertIsNone(orden["nombre_cliente"])
        self.assertEqual(orden["total"], 50.0, "el pedido se conserva sin datos personales")

    def test_retencion_borra_solo_transcripciones_viejas(self):
        self._llamada_con_orden()
        fakes.TABLAS["llamadas"].append({
            "id": "vieja", "restaurante_id": self.rest["id"], "transcripcion": cs.cifrar("hola"),
            "created_at": (datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),
        })
        limite = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        self.assertEqual(db.purgar_transcripciones(limite), 1)
        self.assertIsNone(fakes.TABLAS["llamadas"][1]["transcripcion"])
        self.assertIsNotNone(fakes.TABLAS["llamadas"][0]["transcripcion"])

    def test_cifrar_filas_existentes(self):
        fakes.TABLAS["llamadas"].append({"id": "legado", "restaurante_id": self.rest["id"],
                                         "telefono_cliente": "+525500000000", "transcripcion": "texto plano"})
        self.assertEqual(db.cifrar_filas_existentes()["llamadas"], 1)
        legado = fakes.TABLAS["llamadas"][0]
        self.assertTrue(cs.esta_cifrado(legado["telefono_cliente"]))
        self.assertIsNotNone(legado["telefono_hash"])
        self.assertEqual(db.cifrar_filas_existentes(), {"llamadas": 0, "ordenes": 0}, "debe ser idempotente")


class AgenteTest(CasoBase):
    def test_saludo_sin_aviso_ni_mencion_de_ia(self):
        rest = self.restaurante()
        self.assertEqual(build_saludo(rest), "¡Hola, gracias por llamar a Tacos El Güero! ¿Qué te preparamos hoy?")

    def test_aviso_opcional_neutral(self):
        rest = self.restaurante(aviso_en_llamada=True, url_aviso_privacidad="https://tacoselguero.mx/privacidad")
        saludo = build_saludo(rest)
        self.assertIn("tacoselguero punto m x diagonal privacidad", saludo)
        for palabra in ("virtual", "asistente", "sianka"):
            self.assertNotIn(palabra, saludo.lower())

    def test_reglas_del_prompt(self):
        prompt = build_system_prompt(self.restaurante(), [])
        self.assertIn("No menciones que eres un asistente virtual", prompt)
        self.assertIn("no afirmes ser una persona", prompt)
        self.assertIn("Nunca pidas apellidos, correo, numeros de tarjeta", prompt)


class PaginasPublicasTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.rest = self.restaurante(razon_social="Juan Pérez López", domicilio="Calle 60, Mérida",
                                     email_privacidad="privacidad@tacos.mx")
        self.c = self.cliente()

    def test_aviso_de_sianka(self):
        r = self.c.get("/privacidad")
        self.assertEqual(r.status_code, 200)
        self.assertIn('content="index, follow"', r.text)
        self.assertIn('<link rel="canonical" href="https://sianka.mx/privacidad">', r.text)
        self.assertNotEqual(r.headers.get("cache-control"), "no-store")
        self.assertNotIn("/privacidad/tacos-el-guero", r.text, "no expone la cartera de clientes")
        for proveedor in ("Twilio", "Deepgram", "Anthropic", "Supabase", "AES", "scrypt"):
            self.assertNotIn(proveedor, r.text)
        self.assertIn("pendientes de configurar", r.text, "SIANKA_* estan vacios en las pruebas")

    def test_aviso_del_restaurante(self):
        r = self.c.get("/privacidad/tacos-el-guero")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Juan Pérez López", r.text)
        self.assertIn("privacidad@tacos.mx", r.text)
        self.assertIn('content="noindex, follow"', r.text)
        self.assertNotIn("aún no completa", r.text)
        self.assertNotIn("virtual", r.text)
        self.assertEqual(self.c.get("/privacidad/no-existe").status_code, 404)

    def test_terminos_robots_y_sitemap(self):
        self.assertIn('name="description"', self.c.get("/terminos").text)
        robots = self.c.get("/robots.txt").text
        self.assertIn("Allow: /privacidad", robots)
        self.assertIn("Disallow: /\n", robots)
        self.assertIn("Sitemap: https://sianka.mx/sitemap.xml", robots)
        sitemap = self.c.get("/sitemap.xml")
        self.assertTrue(sitemap.headers["content-type"].startswith("application/xml"))
        self.assertIn("<loc>https://sianka.mx/privacidad</loc>", sitemap.text)
        self.assertNotIn("tacos-el-guero", sitemap.text)
        self.assertIn('href="/privacidad"', self.c.get("/login").text)
