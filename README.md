# Voice Agent — Tacos El Güero

MVP de un **Voice AI Agent** para restaurantes en México. Un cliente marca por
teléfono, una IA le contesta en español y toma su orden hablando de forma
natural, y todo aparece en un dashboard web propio en tiempo real — sin salir
del sistema, sin recargar la página.

## Qué hace

1. El cliente llama al número del restaurante (un número real de Twilio).
2. La IA contesta, saluda mencionando el restaurante, y entiende si el
   cliente quiere ordenar, tiene una duda (horario, ingredientes, precio) o
   quiere otra cosa.
3. Si quiere ordenar, la IA toma el pedido platillo por platillo, repite la
   orden completa en voz alta para confirmar, y la registra en cuanto el
   cliente confirma — nunca inventa platillos fuera del menú real.
4. En cuanto la orden queda confirmada, aparece automáticamente como una
   tarjeta nueva en el dashboard (sin recargar la página), y el restaurante
   la puede mover por su flujo de preparación: **Nueva → Confirmada →
   Preparando → Lista → Entregada**.
5. Mientras la llamada está en curso, el dashboard muestra la transcripción
   en vivo de lo que dice el cliente y lo que responde la IA.

Incluye datos de prueba de un restaurante real de ejemplo: **Tacos El Güero**,
en Mérida, Yucatán, con su menú completo.

## Stack tecnológico

- **FastAPI** + **Uvicorn** — servidor y WebSockets nativos (sin librerías extra de tiempo real)
- **Jinja2** — dashboard renderizado en HTML (sin frontend framework, CSS propio)
- **Twilio Voice + Media Streams** — recibe la llamada y transmite el audio bidireccional en tiempo real
- **Deepgram** — Speech-to-Text streaming en español **y** Text-to-Speech (voces Aura en español)
- **Anthropic Claude** (`claude-haiku-4-5`) — cerebro conversacional, con tool use para registrar la orden de forma estructurada
- **Supabase (PostgreSQL)** — base de datos: restaurantes, menú, llamadas, órdenes

## Estructura del proyecto

```
voice-agent/
├── main.py                    # App FastAPI, registra todos los routers
├── routes/
│   ├── twilio_routes.py       # Webhook de llamadas + WebSocket de Media Stream
│   ├── order_routes.py        # API REST: ordenes, menu, resumen, llamadas
│   └── dashboard_routes.py    # Paginas HTML (Jinja2) + WS del dashboard
├── services/
│   ├── deepgram_service.py    # STT streaming en tiempo real + TTS (Aura)
│   ├── claude_service.py      # Conversacion con Claude + tool use para ordenes
│   └── websocket_manager.py   # Broadcast a los clientes del dashboard
├── database/
│   └── supabase_client.py     # Todas las queries a Supabase
├── templates/                 # dashboard.html, llamadas.html, menu.html
├── static/
│   ├── css/styles.css         # Diseño propio, sin frameworks
│   └── js/dashboard.js        # Cliente WebSocket + actualizacion del DOM
├── prompts/agent_prompt.py    # System prompt dinamico (carga el menu real)
├── models/                    # Modelos Pydantic (order.py, restaurant.py)
└── schema.sql                 # Schema de Supabase + datos de prueba
```

## 1. Requisitos previos

- Python 3.11+
- Una cuenta de [Supabase](https://supabase.com)
- Una cuenta de [Twilio](https://www.twilio.com) con un número de voz real (no de prueba)
- Una API key de [Deepgram](https://deepgram.com) (cubre STT y TTS)
- Una API key de [Anthropic](https://console.anthropic.com) con créditos cargados
- [ngrok](https://ngrok.com) instalado (para exponer tu servidor local a Twilio)

## 2. Instalación

```bash
cd voice-agent
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## 3. Configurar Supabase

1. Crea un proyecto nuevo en Supabase.
2. Ve a **SQL Editor** y ejecuta el contenido completo de `schema.sql`.
   Esto crea las 4 tablas (`restaurantes`, `menus`, `llamadas`, `ordenes`)
   y ya inserta los datos de prueba de **Tacos El Güero** (Mérida, Yucatán)
   con su menú completo.
3. Ve a **Project Settings → API** y copia:
   - `Project URL` → `SUPABASE_URL`
   - `service_role` key → `SUPABASE_KEY` (el backend escribe datos, necesita permisos completos)

## 4. Configurar variables de entorno

Copia `.env.example` a `.env` y llena todos los valores:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

```
TWILIO_ACCOUNT_SID=          # Console de Twilio → Account Info
TWILIO_AUTH_TOKEN=           # Console de Twilio → Account Info
TWILIO_PHONE_NUMBER=         # Tu número de Twilio en formato +52...

DEEPGRAM_API_KEY=            # console.deepgram.com → API Keys (STT y TTS)
DEEPGRAM_TTS_MODEL=aura-2-estrella-es   # voz en español, cambiable

ANTHROPIC_API_KEY=           # console.anthropic.com → API Keys

SUPABASE_URL=
SUPABASE_KEY=

HOST=0.0.0.0
PORT=8000
```

## 5. Levantar el servidor localmente

```bash
python main.py
```

El servidor corre en `http://localhost:8000`. Abre esa URL para ver el
dashboard (estará vacío hasta que entre la primera llamada).

## 6. Exponer el servidor con ngrok (para recibir llamadas de Twilio)

Twilio necesita una URL pública para mandar el webhook de llamadas
entrantes, así que usamos ngrok para exponer tu `localhost:8000`:

```bash
ngrok http 8000
```

Ngrok te dará una URL como `https://a1b2c3d4.ngrok-free.app`. Cópiala.

> El servidor detecta automáticamente el host desde el request de Twilio
> para armar la URL `wss://` del Media Stream — no necesitas configurar
> manualmente el dominio de ngrok en el código.

## 7. Configurar el webhook en Twilio

1. Entra a la [Consola de Twilio](https://console.twilio.com) → **Phone Numbers → Manage → Active Numbers**.
2. Selecciona tu número de voz.
3. En la sección **Voice Configuration**, en **A call comes in**, selecciona
   **Webhook** y pega:

   ```
   https://TU-SUBDOMINIO.ngrok-free.app/webhook/twilio/incoming
   ```

4. Método: `HTTP POST`.
5. Guarda los cambios.

## 8. Probar la llamada

1. Deja corriendo `python main.py` y `ngrok http 8000` en dos terminales.
2. Deja abierto el dashboard en `http://localhost:8000`.
3. Marca al número de Twilio desde tu teléfono.
4. Deberías ver en el dashboard:
   - La sección **"Llamada activa"** aparece con la animación de barras.
   - La transcripción en vivo del cliente y del agente.
   - Al confirmar una orden, una tarjeta nueva aparece en el grid **sin
     recargar la página**, y el pipeline se actualiza en tiempo real.

## Flujo técnico de una llamada

1. El cliente llama → Twilio recibe la llamada.
2. Twilio hace `POST` a `/webhook/twilio/incoming`.
3. FastAPI responde con TwiML (`<Connect><Stream>`) abriendo un Media
   Stream bidireccional hacia `/media-stream`.
4. Deepgram recibe el audio en streaming (mulaw 8kHz) y transcribe en
   tiempo real.
5. Cada utterance final se manda a Claude (Haiku 4.5) junto con el
   historial de la conversación.
6. Claude genera la respuesta en texto y, cuando el cliente confirma su
   pedido, usa la herramienta `registrar_orden` en el mismo turno.
7. Deepgram (voces Aura) convierte la respuesta de texto a audio mulaw 8kHz.
8. El audio se inyecta de vuelta al Media Stream de Twilio.
9. La transcripción en tiempo real se transmite al dashboard vía
   WebSocket (`/ws/dashboard`).
10. Al confirmar la orden: se inserta en Supabase y se hace broadcast del
    evento `orden_nueva` — la tarjeta aparece en el dashboard sin recargar.

Si algo falla durante un turno (la API del LLM, el TTS, la escritura en
Supabase), queda registrado en los logs del servidor y el cliente escucha un
mensaje de disculpa en vez de silencio — la llamada nunca se cae en
silencio sin que quede rastro del error.

## Notas técnicas importantes

- **Modelo de Claude**: se usa `claude-haiku-4-5` — rápido y económico para
  el volumen de llamadas de un restaurante. No se le pasa `thinking` ni
  `output_config.effort`, ya que Haiku 4.5 no los soporta (a diferencia de
  los modelos Opus/Sonnet).
- **Audio**: Deepgram se usa tanto para STT (`nova-2`, streaming) como para
  TTS (voces **Aura**, formato `mulaw` 8kHz sin encabezado — el formato
  nativo que requiere Twilio Media Streams para inyectar audio
  directamente). La voz se controla con `DEEPGRAM_TTS_MODEL` en `.env`.
- **Tool use**: la orden se captura con una herramienta (`registrar_orden`)
  en vez de parsear texto libre — Claude solo la llama cuando el cliente
  confirmó explícitamente toda la orden, con estructura garantizada
  (platillos, cantidades, precios, total).

## Deploy a producción

Para producción, reemplaza ngrok por un dominio propio con HTTPS/WSS real
(Railway, Render, Fly.io, un VPS con Nginx + certificado SSL, etc.) y
actualiza el webhook de Twilio con esa URL final.
