"""Pagina de venta (/): contenido, SEO, contacto y convivencia con el panel."""
import re
from unittest import mock

from services import sitio
from tests.base import CasoBase


class PaginaDeVentaTest(CasoBase):
    def test_contenido_y_seo(self):
        r = self.cliente().get("/")
        self.assertEqual(r.status_code, 200)
        for texto in ('content="index, follow"', '<link rel="canonical" href="https://sianka.mx/">',
                      'property="og:title"', 'id="como-funciona"', 'id="calculadora"', 'data-calculadora',
                      "/static/js/inicio.js", "/static/css/inicio.css", 'href="/privacidad"'):
            self.assertIn(texto, r.text)
        self.assertEqual(len(re.findall(r"<h1[\s>]", r.text)), 1, "un solo h1 por pagina")

    def test_capas_decorativas_ocultas_a_lectores_de_pantalla(self):
        html = self.cliente().get("/").text
        for capa in re.findall(r'<div class="capa [^"]*"[^>]*>', html):
            self.assertIn('aria-hidden="true"', capa)
        for img in re.findall(r"<img [^>]*>", html):
            self.assertIn('alt="', img, "toda imagen lleva alt (vacio si es decorativa)")

    def test_no_promete_cifras_inventadas(self):
        """La pagina no debe afirmar estadisticas de la industria: la unica
        cifra de ventas sale de la calculadora con los datos del visitante."""
        html = self.cliente().get("/").text
        self.assertIsNone(re.search(r"\d+\s?% de (los )?(restaurantes|llamadas|clientes)", html))
        self.assertIn("Datos de ejemplo.", html, "la maqueta del panel se aclara como ejemplo")

    def test_botones_de_contacto_segun_configuracion(self):
        sin_contacto = self.cliente().get("/").text
        self.assertNotIn("wa.me", sin_contacto)

        with mock.patch.object(sitio, "CONTACTO_WHATSAPP", "5219991234567"), \
                mock.patch.object(sitio, "CONTACTO_EMAIL", "ventas@sianka.mx"), \
                mock.patch.object(sitio, "TELEFONO_DEMO", "+529990000000"):
            html = self.cliente().get("/").text
        self.assertIn("https://wa.me/5219991234567?text=", html)
        self.assertIn("mailto:ventas@sianka.mx", html)
        self.assertIn('href="tel:+529990000000"', html)

    def test_con_sesion_la_raiz_es_el_panel(self):
        rest = self.restaurante()
        email, password = self.usuario(rest)
        c = self.cliente()
        self.iniciar_sesion(c, email, password)
        for ruta in ("/", "/panel"):
            with self.subTest(ruta):
                html = c.get(ruta).text
                self.assertIn('data-ventana="pedidos"', html)
                self.assertIn('content="noindex, nofollow"', html)

    def test_login_no_muestra_cuenta_demo_fuera_de_demo(self):
        """El recuadro con correo y contrasena de prueba solo lo activa
        demo.py; en la app normal jamas debe aparecer."""
        html = self.cliente().get("/login").text
        self.assertNotIn("Modo demo", html)
        self.assertNotIn("login-demo", html)

    def test_robots_y_sitemap_incluyen_la_pagina_de_venta(self):
        c = self.cliente()
        robots = c.get("/robots.txt").text
        self.assertIn("Allow: /$", robots)
        self.assertIn("Disallow: /\n", robots, "el resto (panel, api) sigue bloqueado")
        self.assertIn("<loc>https://sianka.mx/</loc>", c.get("/sitemap.xml").text)
