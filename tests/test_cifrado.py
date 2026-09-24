import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

import main
from services import cifrado_service as cs


class CifradoTest(unittest.TestCase):
    def test_ida_y_vuelta(self):
        self.assertEqual(cs.descifrar(cs.cifrar("+529991234567")), "+529991234567")

    def test_mismo_texto_cifra_distinto(self):
        self.assertNotEqual(cs.cifrar("Maria"), cs.cifrar("Maria"))

    def test_texto_anterior_al_cifrado_pasa_tal_cual(self):
        self.assertEqual(cs.descifrar("Maria"), "Maria")

    def test_detecta_alteracion(self):
        cifrado = cs.cifrar("+529991234567")
        alterado = cifrado[:-4] + ("AAAA" if not cifrado.endswith("AAAA") else "BBBB")
        with self.assertRaises(Exception):
            cs.descifrar(alterado)

    def test_huella_no_depende_del_formato(self):
        self.assertEqual(cs.huella_telefono("+52 999 123 4567"), cs.huella_telefono("+529991234567"))

    def test_numero_privado_no_tiene_huella(self):
        self.assertIsNone(cs.huella_telefono("Anonymous"))

    def test_enmascarar(self):
        self.assertEqual(cs.enmascarar_telefono("+529991234567"), "•••• 4567")
        self.assertEqual(cs.enmascarar_telefono("Anonymous"), "Numero privado")


class ArranqueSinClaveTest(unittest.TestCase):
    def test_el_servidor_no_arranca_sin_clave(self):
        with mock.patch.object(cs, "_claves", None), \
                mock.patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "DATA_ENCRYPTION_KEY"):
                with TestClient(main.app):
                    pass
