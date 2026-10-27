"""Ilustracion de cada platillo segun su nombre (static/img/platillos/*.svg).

Se elige por palabras clave, en orden: la primera regla que coincide gana.
Por eso las bebidas van primero ("Agua de horchata" no debe caer en otra
regla) y "Taco de pollo" es taco, no pollo.
"""
import unicodedata

REGLAS: list[tuple[tuple[str, ...], str]] = [
    (("horchata",), "agua-horchata"),
    (("jamaica",), "agua-jamaica"),
    (("agua", "limonada", "tamarindo", "naranjada"), "agua-fresca"),
    (("refresco", "coca", "soda", "lata"), "refresco"),
    (("torta", "sandwich", "cemita", "pambazo"), "torta"),
    (("panucho", "salbut", "tostada", "sope", "gordita", "huarache"), "tostada"),
    (("taco", "cochinita", "bistec", "pastor", "suadero", "carnitas", "asada", "barbacoa", "lechon",
      "tripa", "chorizo", "campechano"), "taco"),
    (("pollo", "alitas", "pechuga"), "pollo"),
]
POR_DEFECTO = "plato"


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_acentos.lower()


def ilustracion(platillo: str | None) -> str:
    """Nombre del archivo (sin extension) de la ilustracion del platillo."""
    nombre = _normalizar(platillo or "")
    for palabras, archivo in REGLAS:
        if any(p in nombre for p in palabras):
            return archivo
    return POR_DEFECTO


def url_ilustracion(platillo: str | None) -> str:
    return f"/static/img/platillos/{ilustracion(platillo)}.svg"
