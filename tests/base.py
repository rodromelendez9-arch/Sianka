import base64
import json
import unittest
from contextlib import contextmanager
from unittest import mock

from fastapi.testclient import TestClient

import main
from database import supabase_client as db
from routes import auth_routes
from routes import twilio_routes as tr
from services import rate_limit_service
from services.auth_service import hashear_password
from tests import fakes

TELEFONO_CLIENTE = "+529991234567"


class CasoBase(unittest.TestCase):
    """Cada prueba empieza con la base vacia y sin intentos de login ni
    peticiones acumuladas de pruebas anteriores."""

    def setUp(self):
        fakes.reiniciar()
        auth_routes._intentos_fallidos.clear()
        rate_limit_service._peticiones.clear()

    # ---------------- Datos ----------------

    def restaurante(self, slug="tacos-el-guero", nombre="Tacos El Güero", **campos) -> dict:
        """Crea el restaurante y devuelve la fila VIVA de la base falsa (los
        cambios que haga la app se ven en este mismo dict)."""
        creado = db.crear_restaurante(slug=slug, nombre=nombre, activo=True, **campos)
        return next(r for r in fakes.TABLAS["restaurantes"] if r["id"] == creado["id"])

    def usuario(self, restaurante: dict, email="dueno@tacos.mx", password="contrasena-segura"):
        fakes.TABLAS["usuarios"].append(
            {"id": f"u-{email}", "restaurante_id": restaurante["id"], "email": email,
             "password_hash": hashear_password(password), "activo": True}
        )
        return email, password

    def platillo(self, restaurante: dict, nombre: str, precio: float) -> dict:
        return db.crear_platillo(restaurante["id"], nombre, precio)

    # ---------------- HTTP ----------------

    def cliente(self) -> TestClient:
        return TestClient(main.app, follow_redirects=False)

    def iniciar_sesion(self, cliente: TestClient, email: str, password: str):
        return cliente.post("/login", data={"email": email, "password": password})

    # ---------------- Llamadas ----------------

    @contextmanager
    def servicios_de_llamada(self, claude_cls):
        """Reemplaza Claude, Deepgram y el TTS durante la llamada y captura
        los eventos que se envian a los paneles."""
        eventos: list[dict] = []

        async def espia(_restaurante_id, evento):
            eventos.append(evento)

        with mock.patch.object(tr, "ClaudeConversationService", claude_cls), \
                mock.patch.object(tr, "DeepgramStreamingService", fakes.FakeDeepgram), \
                mock.patch.object(tr, "sintetizar_audio_mulaw", fakes.fake_tts), \
                mock.patch.object(tr.manager, "broadcast", espia):
            yield eventos

    @staticmethod
    def iniciar_stream(ws, restaurante: dict, telefono=TELEFONO_CLIENTE):
        token = tr._generar_stream_token(restaurante["id"], telefono)
        ws.send_text(json.dumps(
            {"event": "start", "start": {"streamSid": "MZ1", "callSid": "CA1",
                                         "customParameters": {"stream_token": token}}}
        ))

    @staticmethod
    def decir(ws, texto: str, final=True, fin_de_turno=True):
        cmd = {"t": "res", "texto": texto, "final": final, "sf": fin_de_turno}
        ws.send_text(CasoBase._media(cmd))

    @staticmethod
    def silencio(ws):
        """UtteranceEnd de Deepgram: cierra el turno si speech_final no llego."""
        ws.send_text(CasoBase._media({"t": "ue"}))

    @staticmethod
    def _media(cmd: dict) -> str:
        payload = base64.b64encode(json.dumps(cmd).encode()).decode()
        return json.dumps({"event": "media", "media": {"payload": payload}})

    @staticmethod
    def recibir(ws, n: int) -> list[tuple]:
        """Los siguientes `n` mensajes que el servidor manda a Twilio:
        ("media", texto_hablado), ("mark",) o ("clear",)."""
        salida = []
        for _ in range(n):
            m = json.loads(ws.receive_text())
            if m["event"] == "media":
                salida.append(("media", base64.b64decode(m["media"]["payload"]).decode()))
            else:
                salida.append((m["event"],))
        return salida
