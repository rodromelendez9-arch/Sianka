# Voice Agent — Tacos El Güero

MVP de un Voice AI Agent para restaurantes en México. La IA contesta llamadas
reales en español, toma la orden hablando con el cliente, y todo aparece en
un dashboard propio en tiempo real sin salir del sistema.

## Stack

- **FastAPI** + **Uvicorn** — servidor y WebSockets nativos
- **Jinja2** — dashboard renderizado en HTML (sin frontend framework)
- **Twilio Voice + Media Streams** — llamadas telefónicas en tiempo real
- **Deepgram** — Speech-to-Text streaming en español
- **Anthropic Claude** (`claude-opus-5`) — cerebro conversacional con tool use
- **ElevenLabs** — Text-to-Speech en español natural
- **Supabase (PostgreSQL)** — base de datos

## 1. Requisitos previos

- Python 3.11+
- Una cuenta de [Supabase](https://supabase.com)
- Una cuenta de [Twilio](https://www.twilio.com) con un número de voz
- Una API key de [Deepgram](https://deepgram.com)
- Una API key de [Anthropic](https://console.anthropic.com)
- Una cuenta de [ElevenLabs](https://elevenlabs.io) con una voz en español
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
   - `service_role` key (o `anon` key si solo harás lectura) → `SUPABASE_KEY`

## 4. Configurar variables de entorno

Copia `.env.example` a `.env` y llena todos los valores:

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

```
TWILIO_ACCOUNT_SID=       # Console de Twilio → Account Info
TWILIO_AUTH_TOKEN=        # Console de Twilio → Account Info
TWILIO_PHONE_NUMBER=      # Tu número de Twilio en formato +52...

DEEPGRAM_API_KEY=         # console.deepgram.com → API Keys

ANTHROPIC_API_KEY=        # console.anthropic.com → API Keys

ELEVENLABS_API_KEY=       # elevenlabs.io → Profile → API Keys
ELEVENLABS_VOICE_ID=      # Voice Library → elige una voz en español → copia su Voice ID

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

## Estructura del proyecto

```
voice-agent/
├── main.py                    # App FastAPI, registra todos los routers
├── routes/
│   ├── twilio_routes.py       # Webhook de llamadas + WebSocket de Media Stream
│   ├── order_routes.py        # API REST: ordenes, menu, resumen, llamadas
│   └── dashboard_routes.py    # Paginas HTML (Jinja2) + WS del dashboard
├── services/
│   ├── deepgram_service.py    # STT streaming en tiempo real
│   ├── claude_service.py      # Conversacion con Claude + tool use para ordenes
│   ├── elevenlabs_service.py  # TTS a mulaw 8kHz (formato nativo de Twilio)
│   └── websocket_manager.py   # Broadcast a los clientes del dashboard
├── database/
│   └── supabase_client.py     # Todas las queries a Supabase
├── templates/                 # dashboard.html, llamadas.html, menu.html
├── static/
│   ├── css/styles.css         # Diseño propio, sin frameworks
│   └── js/dashboard.js        # Cliente WebSocket + actualizacion del DOM
├── prompts/agent_prompt.py    # System prompt dinamico (carga el menu)
├── models/                    # Modelos Pydantic (order.py, restaurant.py)
└── schema.sql                 # Schema de Supabase + datos de prueba
```

## Flujo técnico de una llamada

1. El cliente llama → Twilio recibe la llamada.
2. Twilio hace `POST` a `/webhook/twilio/incoming`.
3. FastAPI responde con TwiML (`<Connect><Stream>`) abriendo un Media
   Stream bidireccional hacia `/media-stream`.
4. Deepgram recibe el audio en streaming (mulaw 8kHz) y transcribe en
   tiempo real.
5. Cada utterance final se manda a Claude junto con el historial de la
   conversación.
6. Claude genera la respuesta en texto (y usa la herramienta
   `registrar_orden` cuando el cliente confirma su pedido).
7. ElevenLabs convierte la respuesta a audio mulaw 8kHz.
8. El audio se inyecta de vuelta al Media Stream de Twilio.
9. La transcripción en tiempo real se transmite al dashboard vía
   WebSocket (`/ws/dashboard`).
10. Al confirmar la orden: se inserta en Supabase y se hace broadcast del
    evento `orden_nueva` — la tarjeta aparece en el dashboard sin recargar.

## Notas técnicas importantes

- **Audio format**: ElevenLabs se configura con `output_format="ulaw_8000"`
  para generar audio mulaw de 8kHz sin encabezado — es el formato que
  Twilio Media Streams requiere para inyectar audio directamente, sin
  necesidad de convertir desde MP3.
- **Modelo de Claude**: se usa `claude-opus-5` con `thinking` desactivado
  y `effort: "low"` para minimizar la latencia en una llamada de voz en
  tiempo real. Puedes ajustar esto en `services/claude_service.py` si
  prefieres priorizar calidad de razonamiento sobre velocidad.
- **SDK de Deepgram**: el código usa la API de streaming asíncrono del
  `deepgram-sdk`. Si al instalar obtienes una versión distinta del SDK
  con nombres de métodos diferentes, revisa la documentación oficial de
  Deepgram para tu versión exacta (`pip show deepgram-sdk`).

## Deploy a producción

Para producción, reemplaza ngrok por un dominio propio con HTTPS/WSS real
(Railway, Render, Fly.io, un VPS con Nginx + certificado SSL, etc.) y
actualiza el webhook de Twilio con esa URL final.
