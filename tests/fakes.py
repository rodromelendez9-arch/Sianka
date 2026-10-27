"""Dobles de prueba: Supabase en memoria, Deepgram guionado y TTS falso.

La Supabase falsa imita el query builder que usa database/supabase_client.py,
asi las pruebas ejercitan el codigo REAL de esa capa (cifrado al guardar,
filtros por restaurante, ARCO, retencion), no reemplazos de sus funciones.
"""
import copy
import json
import uuid
from datetime import datetime, timezone

TABLAS: dict[str, list[dict]] = {}
# Emula el contador del trigger trg_ordenes_numero_dia (migracion 005).
CONTADORES: dict[tuple, int] = {}


def reiniciar() -> None:
    TABLAS.clear()
    TABLAS.update({t: [] for t in ("restaurantes", "usuarios", "menus", "llamadas", "ordenes")})
    CONTADORES.clear()


class _Resultado:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Consulta:
    def __init__(self, tabla: str):
        self.tabla, self.filtros, self.op, self.valores = tabla, [], "select", None
        self.con_ordenes, self.lim, self.desde = False, None, 0
        self.not_ = self  # solo se usa como .not_.is_(columna, "null")

    def select(self, columnas="*", count=None):
        self.con_ordenes = "ordenes(*)" in columnas
        return self

    def insert(self, fila):
        self.op, self.valores = "insert", fila
        return self

    def update(self, campos):
        self.op, self.valores = "update", campos
        return self

    def eq(self, c, v):
        self.filtros.append(lambda f: f.get(c) == v)
        return self

    def neq(self, c, v):
        self.filtros.append(lambda f: f.get(c) != v)
        return self

    def lt(self, c, v):
        self.filtros.append(lambda f: (f.get(c) or "") < v)
        return self

    def gte(self, c, v):
        self.filtros.append(lambda f: (f.get(c) or "") >= v)
        return self

    def is_(self, c, _valor):
        self.filtros.append(lambda f: f.get(c) is not None)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.lim = n
        return self

    def range(self, desde, hasta):
        self.desde, self.lim = desde, hasta - desde + 1
        return self

    def execute(self):
        filas = TABLAS[self.tabla]
        if self.op == "insert":
            fila = {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), **self.valores}
            if self.tabla == "ordenes":
                clave = (fila["restaurante_id"], datetime.now(timezone.utc).date())
                CONTADORES[clave] = CONTADORES.get(clave, 0) + 1
                fila["numero_dia"] = (CONTADORES[clave] - 1) % 999 + 1
            filas.append(fila)
            return _Resultado([copy.deepcopy(fila)])

        elegidas = [f for f in filas if all(p(f) for p in self.filtros)]
        if self.op == "update":
            for f in elegidas:
                f.update(self.valores)
        elegidas = elegidas[self.desde:]
        salida = copy.deepcopy(elegidas[: self.lim] if self.lim else elegidas)
        if self.con_ordenes:
            for f in salida:
                f["ordenes"] = [copy.deepcopy(o) for o in TABLAS["ordenes"] if o.get("llamada_id") == f["id"]]
        return _Resultado(salida, count=len(salida))


class FakeSupabase:
    def table(self, nombre: str) -> _Consulta:
        return _Consulta(nombre)


def instalar() -> None:
    from database import supabase_client

    reiniciar()
    supabase_client.get_client = lambda: FakeSupabase()


# ---------------- Llamadas ----------------

class FakeDeepgram:
    """El "audio" que manda la prueba es un comando JSON:
    {"t": "res", "texto": ..., "final": bool, "sf": bool} -> transcripcion
    {"t": "ue"}                                            -> UtteranceEnd"""

    def __init__(self, on_transcript, on_utterance_end=None):
        self.on_transcript, self.on_utterance_end = on_transcript, on_utterance_end

    async def start(self):
        pass

    async def send_audio(self, chunk: bytes):
        cmd = json.loads(chunk.decode())
        if cmd["t"] == "res":
            await self.on_transcript(cmd["texto"], cmd.get("final", True), cmd.get("sf", True))
        else:
            await self.on_utterance_end()

    async def finish(self):
        pass


async def fake_tts(texto: str, modelo=None) -> bytes:
    return texto.encode()
