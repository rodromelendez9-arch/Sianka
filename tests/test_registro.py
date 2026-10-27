"""Logs: en Railway salen como JSON con el nivel real (no todo como error)."""
import json
import logging
import unittest
from unittest import mock

from services import registro


class RegistroTest(unittest.TestCase):
    def test_formato_json_lleva_nivel_y_mensaje(self):
        record = logging.LogRecord("uvicorn.error", logging.INFO, __file__, 1, "Arranco %s", ("ok",), None)
        datos = json.loads(registro.FormatoJSON().format(record))
        self.assertEqual(datos["level"], "info")
        self.assertEqual(datos["message"], "Arranco ok")

    def test_json_solo_en_railway_o_si_se_pide(self):
        with mock.patch.dict("os.environ", {"RAILWAY_ENVIRONMENT": "", "LOG_FORMAT": ""}):
            self.assertFalse(registro.usar_json())
        with mock.patch.dict("os.environ", {"RAILWAY_ENVIRONMENT": "production"}):
            self.assertTrue(registro.usar_json())
