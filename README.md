# Sianka

Atención telefónica automatizada para restaurantes en México. El cliente
llama, se le atiende en español de forma natural, se toma su pedido (para
recoger o a domicilio) y la orden aparece al instante en el panel web del
restaurante.

Un mismo despliegue atiende a varios restaurantes: cada uno tiene su número
telefónico, su menú, su configuración y su propio acceso al panel.

## Qué hace

- **Contesta y saluda** en cuanto entra la llamada, con el nombre del restaurante.
- **Toma el pedido** solo con platillos del menú real, pide el nombre de pila y,
  si es a domicilio, dirección, referencias y forma de pago.
- **Valida antes de registrar**: menú, pedido mínimo de envío, dirección, pago.
  El total (con envío) lo calcula el servidor, nunca el modelo.
- **Número de orden del día (001-999)**, que se le dice al cliente para el mostrador.
- **Panel en vivo**: llamada en curso con transcripción, órdenes que llegan sin
  recargar, flujo Nueva → Confirmada → Preparando → Lista → Entregada.
- **Reportes**: platillo más vendido, hora pico, ticket promedio y pronóstico de demanda.
- **Datos personales protegidos**: cifrados, con borrado automático y derechos ARCO.

## Estructura

```
voice-agent/
├── main.py                  # App FastAPI: middleware de seguridad, retención, routers
├── admin.py                 # Altas de restaurantes/usuarios, ARCO, llave de cifrado
├── demo.py                  # Modo demo: el panel con datos de ejemplo, sin .env
├── schema.sql               # Esquema completo para una base nueva
├── migrations/              # Cambios para bases creadas con un schema anterior
├── routes/
│   ├── twilio_routes.py     # Webhook de llamadas, turnos de conversación, registro de órdenes
│   ├── dashboard_routes.py  # Páginas del panel + configuración + WebSocket
│   ├── order_routes.py      # API del panel (/api/*)
│   ├── auth_routes.py       # Login por restaurante
│   └── publico_routes.py    # Avisos de privacidad, términos, robots.txt, sitemap
├── services/
│   ├── claude_service.py    # Conversación y herramienta registrar_orden
│   ├── deepgram_service.py  # Voz a texto (streaming) y texto a voz
│   ├── cifrado_service.py   # Cifrado de datos personales y huella del teléfono
│   ├── auth_service.py      # Contraseñas (scrypt) y sesión por restaurante
│   ├── websocket_manager.py # Eventos en vivo, separados por restaurante
│   ├── sitio.py             # URL pública y datos legales de Sianka
│   └── reportes_service.py, prediccion_service.py, rate_limit_service.py
├── database/supabase_client.py  # Todas las consultas (cifra/descifra aquí)
├── prompts/agent_prompt.py      # Saludo y prompt, armados con los datos de cada restaurante
├── models/                      # Validación de las peticiones del panel
├── templates/ y static/         # Panel (centro de mando, css/panel.css, js/ventanas.js) y páginas públicas
├── static/img/platillos/        # Ilustraciones SVG de los platillos (services/ilustraciones.py las asigna)
├── tests/                       # Pruebas (unittest), sin servicios reales
```

## Ver el panel sin configurar nada (modo demo)

```bash
python demo.py
```

- `http://127.0.0.1:8765` — la página de venta.
- `http://127.0.0.1:8765/login` — entra al panel con la cuenta de prueba, que
  aparece en la misma pantalla de login (solo en modo demo). Trae datos de
  ejemplo y una llamada simulada cada 40 segundos.

No necesita `.env` ni toca ningún servicio real; sirve para revisar el diseño
o para enseñarlo.

## Página de venta y panel

`/` muestra la **página de venta** a los visitantes y el **panel** a quien ya
inició sesión (los restaurantes no cambian su liga). `/panel` lleva siempre al
panel. Los botones de contacto de la página salen de `SIANKA_WHATSAPP`,
`SIANKA_EMAIL_CONTACTO` y `SIANKA_TELEFONO_DEMO` en `.env`.

## Instalación

### 1. Requisitos

- Python 3.11+
- Cuentas de Supabase, Twilio (número de voz real), Deepgram y Anthropic
- ngrok, solo para probar en local

### 2. Dependencias

```bash
python -m venv venv
venv\Scripts\activate          # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
```

### 3. Base de datos (Supabase → SQL Editor)

- **Base nueva:** ejecuta `schema.sql` completo.
- **Base creada con un schema anterior:** ejecuta, en orden, las migraciones
  de `migrations/` que te falten (002 → 005) y después
  `python admin.py cifrar-existentes`.

En **Project Settings → API** copia la URL y la llave `service_role`.

### 4. Variables de entorno

Copia `.env.example` a `.env` y llénalo; cada variable está explicada ahí.
La llave de cifrado es obligatoria (sin ella el servidor no arranca):

```bash
python admin.py generar-clave
```

> **Respalda `DATA_ENCRYPTION_KEY` fuera del servidor.** Si se pierde, los
> teléfonos, nombres, direcciones y transcripciones guardados son irrecuperables.

### 5. Alta del restaurante y su usuario

```bash
python admin.py nuevo-restaurante "Tacos El Güero" --ciudad "Mérida" --twilio +52... --menu menu.csv
python admin.py nuevo-usuario tacos-el-guero dueno@correo.com
```

El CSV del menú lleva los encabezados `platillo,precio,ingredientes`. El resto
(horario, saludo, entregas, datos legales) lo edita el restaurante en
**/configuracion**.

### 6. Correr y conectar Twilio

```bash
python main.py            # http://localhost:8000
ngrok http 8000           # en otra terminal, solo para pruebas locales
```

En la consola de Twilio → **Phone Numbers → Active Numbers** → tu número →
**A call comes in** → Webhook `POST`:

```
https://TU-DOMINIO/webhook/twilio/incoming
```

Marca al número: el panel muestra la llamada en vivo y la orden al confirmarse.

## Operación

| Tarea | Comando |
|---|---|
| Ver restaurantes | `python admin.py listar` |
| Cambiar número, voz o datos | `python admin.py editar-restaurante <slug> --twilio +52...` |
| Importar menú | `python admin.py importar-menu <slug> menu.csv` |
| Cambiar contraseña | `python admin.py cambiar-password <correo>` |
| Derecho de acceso (ARCO) | `python admin.py arco-consultar <slug> <telefono>` |
| Derecho de cancelación (ARCO) | `python admin.py arco-cancelar <slug> <telefono>` |
| Aplicar la retención ya | `python admin.py purgar-transcripciones` |

## Pruebas

```bash
python -m unittest discover -s tests -t .
```

No se conectan a nada real: `tests/__init__.py` fija claves falsas antes de
importar la app y reemplaza Supabase por una base en memoria
(`tests/fakes.py`); Twilio, Deepgram y Anthropic también se simulan. Cubren
el manejo de la llamada, el aislamiento entre restaurantes, el cifrado, ARCO,
la retención, las entregas, la validación de órdenes, el número diario y las
páginas públicas. Córrelas antes de cada commit.

## Cómo funciona una llamada

1. Twilio llama al webhook; el número marcado identifica al restaurante y se
   abre el stream de audio con un token firmado de corta vida.
2. Se reproduce el saludo de inmediato (texto fijo, sin esperar al modelo).
3. La voz del cliente se transcribe en streaming; el turno se cierra cuando el
   cliente deja de hablar, y los turnos se procesan uno a la vez. Si el
   cliente habla encima, el audio del agente se corta.
4. Al confirmar, el modelo llama `registrar_orden`; el servidor valida y
   recalcula, guarda la orden (la base le asigna el número del día) y le
   devuelve al modelo el resultado real para que confirme total y número, o
   explique qué falta.
5. La orden llega al panel del restaurante por WebSocket.

## Datos personales

- Teléfono, nombre, transcripción y datos de entrega se guardan cifrados
  (AES-256-GCM). El panel muestra el teléfono enmascarado, salvo en pedidos a
  domicilio (el repartidor lo necesita).
- Transcripciones y datos de entrega se borran solos a los
  `RETENCION_TRANSCRIPCIONES_DIAS` (90 por defecto).
- Cada restaurante solo ve sus propios datos; RLS activo en todas las tablas.
- Avisos públicos en `/privacidad`, `/privacidad/<slug>` y `/terminos`.

## Producción (Railway)

`railway.json` ya trae el comando de arranque (uvicorn detrás del proxy de
Railway, para que la IP real del cliente llegue al límite de intentos y la
firma de Twilio se valide con `https`), el healthcheck `/health` y **una sola
réplica**: el límite de intentos y los eventos en vivo viven en memoria, así
que no escales a más réplicas hasta moverlos a un almacén compartido.
`.python-version` fija Python 3.12.

1. Railway → **New Project → Deploy from GitHub repo** → este repositorio.
2. **Variables**: las de `.env.example`. Obligatorias: `TWILIO_AUTH_TOKEN`,
   `DEEPGRAM_API_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`,
   `SESSION_SECRET_KEY`, `DATA_ENCRYPTION_KEY` (la **misma** que tu `.env`
   local, porque `admin.py` la usa para cifrar) y `PUBLIC_BASE_URL`. No pongas
   `PORT` ni `HOST`: Railway asigna el puerto.
3. **Settings → Networking → Generate Domain** (o tu dominio propio) y pon esa
   URL en `PUBLIC_BASE_URL`.
4. En Twilio apunta el número a `https://TU-DOMINIO/webhook/twilio/incoming` (POST).
