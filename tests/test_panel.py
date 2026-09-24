"""Panel del restaurante: ilustraciones, centro de mando, graficas y CSP."""
import re
import unittest
from datetime import datetime, timezone

from routes.dashboard_routes import _fecha
from services.ilustraciones import ilustracion
from services.reportes_service import calcular_reporte
from tests import fakes
from tests.base import CasoBase


class IlustracionesTest(unittest.TestCase):
    def test_elige_por_palabras_clave(self):
        casos = {
            "Cochinita pibil": "taco",
            "Taco de pollo": "taco",  # "taco" gana a "pollo"
            "Pollo asado": "pollo",
            "Agua de horchata": "agua-horchata",
            "Agua de Jamaica": "agua-jamaica",
            "Limonada": "agua-fresca",
            "Refresco": "refresco",
            "Torta de pierna": "torta",
            "Panucho de relleno negro": "tostada",
            "Salbutes": "tostada",
            "Lechón al horno": "taco",  # sin acentos al comparar
            "Flan napolitano": "plato",  # sin regla: ilustracion generica
            "": "plato",
        }
        for platillo, esperado in casos.items():
            with self.subTest(platillo):
                self.assertEqual(ilustracion(platillo), esperado)


class FechaTest(unittest.TestCase):
    def test_formato_legible_en_hora_de_mexico(self):
        self.assertEqual(_fecha("2026-09-24T02:15:33+00:00"), "23 sep · 20:15")
        self.assertEqual(_fecha(None), "—")


class ReportesGraficasTest(unittest.TestCase):
    def test_distribuciones_completas(self):
        ordenes = [
            {"total": 50, "created_at": "2026-09-21T20:00:00-06:00",
             "items": [{"platillo": "Bistec", "cantidad": 2, "subtotal": 56}]},
            {"total": 25, "created_at": "2026-09-21T21:00:00-06:00",
             "items": [{"platillo": "Pollo asado", "cantidad": 1, "subtotal": 25}]},
        ]
        llamadas = [{"created_at": "2026-09-21T20:10:00-06:00"}, {"created_at": "2026-09-21T20:40:00-06:00"}]
        graficas = calcular_reporte(ordenes, llamadas)["graficas"]
        self.assertEqual(len(graficas["llamadas_por_hora"]), 24)
        self.assertEqual(graficas["llamadas_por_hora"][20], 2)
        self.assertEqual([d["dia"] for d in graficas["ordenes_por_dia"]][0], "Lunes")
        self.assertEqual(graficas["ordenes_por_dia"][0]["ordenes"], 2)  # 21 sep 2026 es lunes
        self.assertEqual(graficas["platillos_top"][0]["platillo"], "Bistec")


class CentroDeMandoTest(CasoBase):
    def setUp(self):
        super().setUp()
        self.rest = self.restaurante(twilio_number="+529990000001")
        self.platillo(self.rest, "Cochinita pibil", 25)
        agotado = self.platillo(self.rest, "Refresco", 18)
        next(m for m in fakes.TABLAS["menus"] if m["id"] == agotado["id"])["disponible"] = False
        self.email, self.password = self.usuario(self.rest)
        self.c = self.cliente()
        self.iniciar_sesion(self.c, self.email, self.password)

    def test_ventanas_y_menu_rapido(self):
        panel = self.c.get("/").text
        for ventana in ("llamada", "hoy", "pedidos", "entregas", "menu"):
            self.assertIn(f'data-ventana="{ventana}"', panel)
        self.assertIn('data-rapido-toggle=', panel)
        self.assertIn('class="platillo-rapido agotado"', panel, "el agotado se ve marcado")
        self.assertIn("/static/img/platillos/taco.svg", panel)

    def test_grafica_de_hoy_cuenta_por_hora_local(self):
        from database import supabase_client as db

        db.crear_orden(self.rest["id"], None, [], 10.0)
        panel = self.c.get("/").text
        datos = re.search(r'<script type="application/json" id="datos-hoy">(.*?)</script>', panel).group(1)
        import json

        por_hora = json.loads(datos)["ordenes_por_hora"]
        self.assertEqual(len(por_hora), 24)
        self.assertEqual(sum(por_hora), 1)

    def test_menu_y_reportes_con_ilustraciones(self):
        from database import supabase_client as db

        self.assertIn("/static/img/platillos/taco.svg", self.c.get("/menu").text)
        self.assertNotIn('id="datos-reportes"', self.c.get("/reportes").text, "sin datos no hay graficas")

        db.crear_orden(self.rest["id"], None, [{"platillo": "Cochinita pibil", "cantidad": 2, "subtotal": 50}], 50.0)
        reportes = self.c.get("/reportes").text
        self.assertIn('id="datos-reportes"', reportes)
        self.assertIn("/static/img/platillos/taco.svg", reportes, "ranking con ilustracion")

    def test_ninguna_pagina_trae_estilos_ni_scripts_en_linea(self):
        """La CSP (style-src/script-src 'self') bloquea <style>, style="" y
        <script> con codigo en linea: el login se mostro sin formato por un
        <style> en la plantilla. Los <script type="application/json"> son
        datos, no codigo, y si estan permitidos."""
        paginas = ["/", "/llamadas", "/menu", "/reportes", "/configuracion", "/privacidad",
                   "/privacidad/tacos-el-guero", "/terminos"]
        paginas_sin_sesion = ["/login"]
        for ruta in paginas + paginas_sin_sesion:
            with self.subTest(ruta):
                html = (self.cliente() if ruta in paginas_sin_sesion else self.c).get(ruta).text
                self.assertNotIn("<style", html)
                self.assertIsNone(re.search(r'\sstyle="', html), "atributo style en linea")
                for script in re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", html):
                    self.assertIn('type="application/json"', script, "script con codigo en linea")

    def test_estaticos_del_diseno_existen(self):
        for ruta in ("/static/css/panel.css", "/static/js/ventanas.js", "/static/js/graficas.js",
                     "/static/js/reportes.js", "/static/img/platillos/plato.svg"):
            with self.subTest(ruta):
                self.assertEqual(self.c.get(ruta).status_code, 200)

    def test_orden_en_vivo_trae_ilustraciones(self):
        from routes import twilio_routes as tr

        class Claude:
            def __init__(self, *a, **k):
                self.saludo = "Hola"

            async def responder(self, texto, registrar_orden):
                ok, msg = await registrar_orden({"nombre_cliente": "Ana", "tipo_entrega": "recoger",
                                                 "items": [{"platillo": "Cochinita pibil", "cantidad": 1}]})
                return {"texto": msg, "orden_registrada": ok}

        with self.servicios_de_llamada(Claude) as eventos, self.cliente() as c, \
                c.websocket_connect("/media-stream") as ws:
            self.iniciar_stream(ws, self.rest)
            self.recibir(ws, 2)
            self.decir(ws, "una de cochinita")
            self.recibir(ws, 2)
            ws.send_text('{"event": "stop"}')
        nueva = next(e for e in eventos if e["evento"] == "orden_nueva")
        self.assertEqual(nueva["items"][0]["ilustracion"], "/static/img/platillos/taco.svg")
        self.assertIs(tr.ClaudeConversationService.__name__, "ClaudeConversationService", "el mock se restauro")
        _ = datetime.now(timezone.utc)
