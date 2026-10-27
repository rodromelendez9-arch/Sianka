"""Modo demo: el panel real con datos de ejemplo, para verlo o ensenarlo.

    python demo.py
      http://127.0.0.1:8765        pagina de venta
      http://127.0.0.1:8765/panel  panel del restaurante (sin login)

- Usa la base en memoria de las pruebas (tests/fakes.py) y claves falsas: NO
  toca Supabase, Twilio, Deepgram ni Anthropic, ni necesita el .env.
- Entra directo al panel sin login y cada 40 s simula una llamada completa
  (transcripcion en vivo y orden nueva), para ver el centro de mando en accion.
- Solo escucha en 127.0.0.1 (esta computadora). No es para produccion.
"""
import os
import random
import sys
from datetime import datetime, timedelta, timezone

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # templates/ y static/ son rutas relativas
sys.path.insert(0, os.getcwd())
import tests  # noqa: E402,F401  (claves falsas + base en memoria)
from tests import fakes  # noqa: E402
from database import supabase_client as db  # noqa: E402

random.seed(7)
ahora = datetime.now(timezone.utc)

rest = db.crear_restaurante(
    slug="tacos-el-guero", nombre="Tacos El Güero", ciudad="Mérida, Yucatán", activo=True,
    horario="Lunes a domingo de 13:00 a 23:00", twilio_number="+529990000001",
    ofrece_entregas=True, costo_envio=30, pedido_minimo_envio=100, tiempo_entrega_min=40,
    zona_entrega="Centro, García Ginerés e Itzimná", razon_social="Juan Pérez López",
    domicilio="Calle 60 #500, Centro, Mérida", email_privacidad="privacidad@tacoselguero.mx",
)
rid = rest["id"]

MENU = [
    ("Cochinita pibil", 25, "Cochinita, cebolla morada, habanero, tortilla de maíz"),
    ("Bistec", 28, "Bistec, cebolla, cilantro, tortilla de maíz"),
    ("Pollo asado", 25, "Pollo asado, lechuga, tomate"),
    ("Panucho de relleno negro", 32, "Relleno negro, huevo, frijol colado"),
    ("Agua de horchata", 20, "Agua fresca de horchata"),
    ("Agua de jamaica", 20, "Agua fresca de jamaica"),
    ("Refresco", 18, "Refresco de lata"),
]
for nombre, precio, ingredientes in MENU:
    db.crear_platillo(rid, nombre, precio, ingredientes)
fakes.TABLAS["menus"][-1]["disponible"] = False  # un platillo agotado

NOMBRES = ["María", "Luis", "Ana", "Jorge", "Sofía", "Carlos", "Fernanda", "Diego", "Valeria", "Pedro"]
DIRECCIONES = ["Calle 59 #512 x 62 y 64, Centro", "Calle 21 #88, García Ginerés", "Calle 17 #301, Itzimná"]


def items_al_azar():
    elegidos = random.sample(MENU[:6], random.randint(1, 3))
    items = []
    for nombre, precio, _ in elegidos:
        cantidad = random.randint(1, 4)
        items.append({"platillo": nombre, "cantidad": cantidad, "precio": float(precio), "subtotal": float(precio * cantidad)})
    return items, sum(i["subtotal"] for i in items)


# Historial de 8 semanas para reportes y pronostico
for dias_atras in range(1, 56):
    for _ in range(random.randint(4, 14)):
        momento = (ahora - timedelta(days=dias_atras)).replace(hour=random.choice([19, 20, 20, 21, 1, 2, 3]),
                                                              minute=random.randint(0, 59))
        llamada = db.crear_llamada(rid, f"+52999{random.randint(1000000, 9999999)}")
        fila_llamada = fakes.TABLAS["llamadas"][-1]
        fila_llamada.update(created_at=momento.isoformat(), duracion_segundos=random.randint(45, 240))
        if random.random() < 0.75:
            items, total = items_al_azar()
            db.crear_orden(rid, llamada["id"], items, total, "20 minutos", nombre_cliente=random.choice(NOMBRES))
            fakes.TABLAS["ordenes"][-1].update(created_at=momento.isoformat(), status="entregada")
            fila_llamada["resultado"] = "orden"
        else:
            fila_llamada["resultado"] = "sin_orden"

# Ordenes ya entregadas en las horas previas de HOY (para la grafica del dia)
ahora_local = datetime.now().astimezone()
for horas_atras in range(1, 11):
    for _ in range(random.choice([1, 2, 2, 3, 4, 5, 3, 2])):
        momento = ahora - timedelta(hours=horas_atras, minutes=random.randint(0, 59))
        if momento.astimezone().date() != ahora_local.date():
            continue
        items, total = items_al_azar()
        llamada = db.crear_llamada(rid, f"+52999{random.randint(1000000, 9999999)}")
        fakes.TABLAS["llamadas"][-1].update(created_at=momento.isoformat(), resultado="orden",
                                            duracion_segundos=random.randint(50, 200))
        db.crear_orden(rid, llamada["id"], items, total, "20 minutos", nombre_cliente=random.choice(NOMBRES))
        fakes.TABLAS["ordenes"][-1].update(created_at=momento.isoformat(), status="entregada")
        if random.random() < 0.3:  # algunas llamadas no terminan en pedido (dudas, horario...)
            db.crear_llamada(rid, f"+52999{random.randint(1000000, 9999999)}")
            fakes.TABLAS["llamadas"][-1].update(created_at=momento.isoformat(), resultado="sin_orden",
                                                duracion_segundos=random.randint(20, 90))

# Ordenes activas de hoy, en distintos estados
fakes.CONTADORES.clear()
activas = [
    ("nueva", "domicilio"), ("nueva", "recoger"), ("confirmada", "recoger"),
    ("preparando", "domicilio"), ("preparando", "recoger"), ("lista", "recoger"),
]
for minutos, (status, tipo) in zip((2, 5, 11, 18, 24, 31), activas):
    items, subtotal = items_al_azar()
    telefono = f"+52999{random.randint(1000000, 9999999)}"
    llamada = db.crear_llamada(rid, telefono)
    db.actualizar_llamada(llamada["id"], resultado="orden", duracion_segundos=random.randint(60, 200),
                          nombre_cliente=random.choice(NOMBRES),
                          transcripcion="Agente: ¡Hola, gracias por llamar a Tacos El Güero! ¿Qué te preparamos hoy?\n"
                                        "Cliente: Quiero unos tacos de cochinita.")
    extra = {}
    total = subtotal
    if tipo == "domicilio":
        total = subtotal + 30
        extra = dict(tipo_entrega="domicilio", costo_envio=30.0, direccion_entrega=random.choice(DIRECCIONES),
                     referencias_entrega="Fachada amarilla, portón negro", telefono_contacto=telefono,
                     metodo_pago="efectivo", paga_con=float((int(total) // 100 + 1) * 100))
    db.crear_orden(rid, llamada["id"], items, total, "40 minutos" if tipo == "domicilio" else "20 minutos",
                   nombre_cliente=random.choice(NOMBRES), **extra)
    momento = (ahora - timedelta(minutes=minutos)).isoformat()
    fakes.TABLAS["ordenes"][-1].update(status=status, created_at=momento)
    fakes.TABLAS["llamadas"][-1]["created_at"] = momento

import uvicorn  # noqa: E402

import main  # noqa: E402
from services.auth_service import require_login  # noqa: E402

# SOLO para esta demo local: entra directo como el restaurante, sin login.
main.app.dependency_overrides[require_login] = lambda: rid
from routes import dashboard_routes  # noqa: E402

# Sesion forzada solo para el WebSocket del panel: asi "/" sigue mostrando la
# pagina de venta y /panel (require_login sobrescrito arriba) el panel.
dashboard_routes.restaurante_de_sesion = lambda conexion: rid if conexion.scope["type"] == "websocket" else None

# ---------------- Llamada simulada cada 40 s ----------------
import asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

from services.ilustraciones import url_ilustracion  # noqa: E402
from services.websocket_manager import manager  # noqa: E402

GUIONES = [
    ("Sofía", [("cliente", "Hola, buenas tardes, quiero hacer un pedido"),
               ("agente", "¡Claro! ¿Qué te preparamos?"),
               ("cliente", "Tres de cochinita y una horchata grande"),
               ("agente", "Perfecto. ¿A nombre de quién y es para recoger o a domicilio?"),
               ("cliente", "A nombre de Sofía, paso a recogerlo"),
               ("agente", "Listo Sofía, son 95 pesos. Tu orden es la número siete, en 20 minutos.")],
     [("Cochinita pibil", 3, 25), ("Agua de horchata", 1, 20)], "recoger"),
    ("Pedro", [("cliente", "Qué tal, ¿hacen envíos a García Ginerés?"),
               ("agente", "Sí, el envío cuesta 30 pesos. ¿Qué vas a querer?"),
               ("cliente", "Dos panuchos de relleno negro y dos de bistec"),
               ("agente", "¿Me das tu dirección con referencias?"),
               ("cliente", "Calle 21 número 88, casa azul con portón blanco"),
               ("agente", "Gracias Pedro, son 150 pesos con envío. Llega en 40 minutos.")],
     [("Panucho de relleno negro", 2, 32), ("Bistec", 2, 28)], "domicilio"),
]


async def simular_llamadas():
    await asyncio.sleep(6)
    turno = 0
    while True:
        nombre, lineas, items, tipo = GUIONES[turno % len(GUIONES)]
        turno += 1
        telefono = f"+52999{random.randint(1000000, 9999999)}"
        await manager.broadcast(rid, {"evento": "llamada_activa", "telefono_cliente": f"•••• {telefono[-4:]}"})
        for hablante, texto in lineas:
            if hablante == "cliente":
                palabras = texto.split()
                for n in range(2, len(palabras), 3):  # fragmentos provisionales, como Deepgram
                    await manager.broadcast(rid, {"evento": "transcripcion", "hablante": "cliente",
                                                  "texto": " ".join(palabras[:n]), "es_final": False})
                    await asyncio.sleep(0.45)
            await manager.broadcast(rid, {"evento": "transcripcion", "hablante": hablante, "texto": texto, "es_final": True})
            await asyncio.sleep(1.8)

        detalle = [{"platillo": p, "cantidad": c, "precio": float(pr), "subtotal": float(c * pr)} for p, c, pr in items]
        subtotal = sum(i["subtotal"] for i in detalle)
        extra = {}
        if tipo == "domicilio":
            extra = dict(tipo_entrega="domicilio", costo_envio=30.0, direccion_entrega="Calle 21 #88, García Ginerés",
                         referencias_entrega="Casa azul, portón blanco", telefono_contacto=telefono,
                         metodo_pago="efectivo", paga_con=200.0)
        total = subtotal + (30 if tipo == "domicilio" else 0)
        orden = db.crear_orden(rid, None, detalle, total, "40 minutos" if tipo == "domicilio" else "20 minutos",
                               nombre_cliente=nombre, **extra)
        await manager.broadcast(rid, {
            "evento": "orden_nueva", "orden_id": orden["id"], "numero_dia": orden["numero_dia"],
            "items": [{**i, "ilustracion": url_ilustracion(i["platillo"])} for i in detalle],
            "total": total, "recoleccion": orden["tiempo_recoleccion"], "nombre_cliente": nombre,
            "tipo_entrega": tipo, "costo_envio": extra.get("costo_envio", 0),
            "direccion_entrega": extra.get("direccion_entrega"), "referencias_entrega": extra.get("referencias_entrega"),
            "telefono_contacto": extra.get("telefono_contacto"), "metodo_pago": extra.get("metodo_pago"),
            "paga_con": extra.get("paga_con"), "status": "nueva", "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        await asyncio.sleep(3)
        await manager.broadcast(rid, {"evento": "llamada_terminada"})
        await asyncio.sleep(40)


lifespan_original = main.app.router.lifespan_context


@asynccontextmanager
async def lifespan_demo(app):
    async with lifespan_original(app):
        tarea = asyncio.create_task(simular_llamadas())
        yield
        tarea.cancel()

main.app.router.lifespan_context = lifespan_demo

print("Demo lista:", flush=True)
print("  Pagina de venta  http://127.0.0.1:8765", flush=True)
print("  Panel            http://127.0.0.1:8765/panel", flush=True)
uvicorn.run(main.app, host="127.0.0.1", port=8765, log_level="warning")
