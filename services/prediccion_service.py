from collections import Counter, defaultdict
from typing import Any, Optional

from services.reportes_service import DIAS_SEMANA, a_hora_local, formatear_hora

MUESTRAS_CONFIANZA_ALTA = 8
MUESTRAS_CONFIANZA_MEDIA = 3


def calcular_prediccion_demanda(
    ordenes: list[dict[str, Any]],
    llamadas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pronostico de demanda por dia de la semana usando promedio estacional
    (seasonal naive): el promedio historico de ese mismo dia de la semana.

    Es deliberadamente simple. Con pocas semanas de historial, un modelo
    complejo (ARIMA, redes neuronales) se sobreajusta a ruido y da numeros
    con apariencia de precision que en realidad son inventados. El promedio
    estacional es el punto de partida estandar en pronostico de series de
    tiempo cortas y ruidosas -- es transparente, y mejora solo con mas datos
    reales, sin cambiar de metodo despues.

    `ordenes` y `llamadas` deben venir de un periodo de varias semanas
    (ver get_ordenes_periodo/get_llamadas_periodo con un `desde_iso` amplio).
    """
    ordenes_por_semana_dia: dict[tuple[int, int], int] = defaultdict(int)
    llamadas_por_semana_dia: dict[tuple[int, int], int] = defaultdict(int)
    horas_llamadas_por_dia: dict[int, list[int]] = defaultdict(list)

    for orden in ordenes:
        creado = orden.get("created_at")
        if not creado:
            continue
        dt = a_hora_local(creado)
        clave = (dt.isocalendar()[1], dt.weekday())
        ordenes_por_semana_dia[clave] += 1

    for llamada in llamadas:
        creado = llamada.get("created_at")
        if not creado:
            continue
        dt = a_hora_local(creado)
        clave = (dt.isocalendar()[1], dt.weekday())
        llamadas_por_semana_dia[clave] += 1
        horas_llamadas_por_dia[dt.weekday()].append(dt.hour)

    ordenes_por_dia: dict[int, list[int]] = defaultdict(list)
    for (_semana, dia), cantidad in ordenes_por_semana_dia.items():
        ordenes_por_dia[dia].append(cantidad)

    llamadas_por_dia: dict[int, list[int]] = defaultdict(list)
    for (_semana, dia), cantidad in llamadas_por_semana_dia.items():
        llamadas_por_dia[dia].append(cantidad)

    pronostico: list[dict[str, Any]] = []

    for dia in range(7):
        muestras_ordenes = ordenes_por_dia.get(dia, [])
        muestras_llamadas = llamadas_por_dia.get(dia, [])
        horas = horas_llamadas_por_dia.get(dia, [])

        ordenes_esperadas = round(sum(muestras_ordenes) / len(muestras_ordenes), 1) if muestras_ordenes else 0.0
        llamadas_esperadas = round(sum(muestras_llamadas) / len(muestras_llamadas), 1) if muestras_llamadas else 0.0

        hora_pico_estimada: Optional[str] = None
        if horas:
            hora, _cantidad = Counter(horas).most_common(1)[0]
            hora_pico_estimada = formatear_hora(hora)

        num_muestras = max(len(muestras_ordenes), len(muestras_llamadas))
        confianza = _nivel_confianza(num_muestras)

        pronostico.append(
            {
                "dia": DIAS_SEMANA[dia],
                "dia_index": dia,
                "ordenes_esperadas": ordenes_esperadas,
                "llamadas_esperadas": llamadas_esperadas,
                "hora_pico_estimada": hora_pico_estimada,
                "muestras": num_muestras,
                "confianza": confianza,
            }
        )

    return pronostico


def _nivel_confianza(num_muestras: int) -> str:
    if num_muestras >= MUESTRAS_CONFIANZA_ALTA:
        return "alta"
    if num_muestras >= MUESTRAS_CONFIANZA_MEDIA:
        return "media"
    if num_muestras >= 1:
        return "baja"
    return "sin_datos"
