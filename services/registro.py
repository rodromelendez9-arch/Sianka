"""Configuracion de logs.

Uvicorn escribe sus mensajes en stderr y Railway marca todo stderr como
error, asi que un arranque normal aparecia en rojo. Aqui todo sale por
stdout; en Railway (o con LOG_FORMAT=json) cada linea es un JSON con
"level", que Railway usa para mostrar la severidad real. Tambien da un
handler a los loggers de la app, que sin esto perdian sus mensajes INFO.
"""
import json
import logging
import logging.config
import os
import sys
from datetime import datetime, timezone


class FormatoJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        datos = {
            "message": record.getMessage(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
        }
        if record.exc_info:
            datos["exception"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False)


def usar_json() -> bool:
    return os.getenv("LOG_FORMAT", "").lower() == "json" or bool(os.getenv("RAILWAY_ENVIRONMENT"))


def configurar() -> None:
    nivel = os.getenv("LOG_LEVEL", "INFO").upper()
    formato = (
        {"()": FormatoJSON}
        if usar_json()
        else {"format": "%(levelname)s:     %(name)s - %(message)s"}
    )
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"app": formato},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "stream": sys.stdout, "formatter": "app"},
        },
        "root": {"handlers": ["stdout"], "level": nivel},
        # Los de uvicorn traen su propio handler a stderr: se reemplaza.
        "loggers": {
            **{
                nombre: {"handlers": ["stdout"], "level": nivel, "propagate": False}
                for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access")
            },
            # httpx registra en INFO cada consulta a Supabase con sus filtros;
            # no aporta y llenaria los logs de datos de las consultas.
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
        },
    })
