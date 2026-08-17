import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_TTS_MODEL = os.getenv("DEEPGRAM_TTS_MODEL", "aura-2-estrella-es")

logger = logging.getLogger(__name__)

TranscriptCallback = Callable[[str, bool], Awaitable[None]]
UtteranceEndCallback = Callable[[], Awaitable[None]]


class DeepgramStreamingService:
    """Maneja una conexion de streaming STT (Deepgram) para una sola llamada.

    Usa el SDK deepgram-sdk 7.x (cliente generado con Fern): la conexion es
    un context manager asincrono (`client.listen.v1.connect(...)`) que se
    entra y se sale manualmente para que dure toda la llamada telefonica.
    """

    def __init__(
        self,
        on_transcript: TranscriptCallback,
        on_utterance_end: Optional[UtteranceEndCallback] = None,
    ) -> None:
        if not DEEPGRAM_API_KEY:
            raise RuntimeError("DEEPGRAM_API_KEY no esta configurado en .env")

        self.on_transcript = on_transcript
        self.on_utterance_end = on_utterance_end

        self._client = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)
        self._connection_cm = None
        self._socket = None
        self._listen_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._connection_cm = self._client.listen.v1.connect(
            model="nova-2",
            language="es",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            punctuate="true",
            interim_results="true",
            smart_format="true",
            utterance_end_ms=1000,
            vad_events="true",
        )
        self._socket = await self._connection_cm.__aenter__()
        self._socket.on(EventType.MESSAGE, self._on_message)
        self._listen_task = asyncio.create_task(self._socket.start_listening())

    def _on_message(self, message: Any) -> None:
        tipo = getattr(message, "type", None)

        if tipo == "Results":
            alternativas = message.channel.alternatives
            if not alternativas:
                return
            transcript = alternativas[0].transcript
            if not transcript:
                return
            task = asyncio.create_task(self.on_transcript(transcript, message.is_final))
            task.add_done_callback(self._log_task_exception)
        elif tipo == "UtteranceEnd" and self.on_utterance_end:
            task = asyncio.create_task(self.on_utterance_end())
            task.add_done_callback(self._log_task_exception)

    @staticmethod
    def _log_task_exception(task: "asyncio.Task[Any]") -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.exception("Excepcion no manejada en callback de Deepgram", exc_info=exc)

    async def send_audio(self, chunk: bytes) -> None:
        if self._socket:
            await self._socket.send_media(chunk)

    async def finish(self) -> None:
        if self._socket:
            await self._socket.send_close_stream()

        if self._listen_task:
            self._listen_task.cancel()
            self._listen_task = None

        if self._connection_cm:
            await self._connection_cm.__aexit__(None, None, None)
            self._connection_cm = None

        self._socket = None


async def sintetizar_audio_mulaw(texto: str) -> bytes:
    """Convierte texto a audio mulaw 8kHz sin encabezado (formato que Twilio
    Media Streams requiere), usando Deepgram Aura TTS."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY no esta configurado en .env")

    client = AsyncDeepgramClient(api_key=DEEPGRAM_API_KEY)

    audio_stream = client.speak.v1.audio.generate(
        text=texto,
        model=DEEPGRAM_TTS_MODEL,
        encoding="mulaw",
        sample_rate=8000,
        container="none",
    )

    audio_bytes = bytearray()
    async for chunk in audio_stream:
        audio_bytes.extend(chunk)

    return bytes(audio_bytes)
