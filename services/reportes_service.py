from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

ZONA_HORARIA = ZoneInfo("America/Mexico_City")

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def a_hora_local(iso_timestamp: str) -> datetime:
    """Compartida con prediccion_service.py -- mismo criterio de zona horaria en todo el analisis."""
    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return dt.astimezone(ZONA_HORARIA)


def formatear_hora(hora: int) -> str:
    if hora == 0:
        return "12:00 AM"
    if hora < 12:
        return f"{hora}:00 AM"
    if hora == 12:
        return "12:00 PM"
    return f"{hora - 12}:00 PM"


def calcular_reporte(ordenes: list[dict[str, Any]], llamadas: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrega ordenes y llamadas de un periodo en las metricas del reporte.

    Se hace en Python (no en SQL) porque PostgREST no expresa bien
    agregaciones sobre el campo JSONB `items` ni bucketing por hora/dia,
    y el volumen esperado (un restaurante, cientos de ordenes) no lo justifica.
    """
    platillos_cantidad: Counter = Counter()
    platillos_ingreso: dict[str, float] = defaultdict(float)
    ordenes_por_dia: Counter = Counter()

    total_ordenes = len(ordenes)
    ingreso_total = 0.0

    for orden in ordenes:
        ingreso_total += float(orden.get("total") or 0)

        creado = orden.get("created_at")
        if creado:
            dia = DIAS_SEMANA[a_hora_local(creado).weekday()]
            ordenes_por_dia[dia] += 1

        for item in orden.get("items") or []:
            platillo = item.get("platillo")
            if not platillo:
                continue
            platillos_cantidad[platillo] += int(item.get("cantidad") or 0)
            platillos_ingreso[platillo] += float(item.get("subtotal") or 0)

    llamadas_por_hora: Counter = Counter()
    for llamada in llamadas:
        creado = llamada.get("created_at")
        if creado:
            llamadas_por_hora[a_hora_local(creado).hour] += 1

    platillo_top: Optional[dict[str, Any]] = None
    if platillos_cantidad:
        nombre, cantidad = platillos_cantidad.most_common(1)[0]
        platillo_top = {
            "platillo": nombre,
            "cantidad": cantidad,
            "ingreso": round(platillos_ingreso[nombre], 2),
        }

    hora_pico: Optional[dict[str, Any]] = None
    if llamadas_por_hora:
        hora, cantidad = llamadas_por_hora.most_common(1)[0]
        hora_pico = {
            "hora": hora,
            "etiqueta": formatear_hora(hora),
            "llamadas": cantidad,
        }

    dia_mas_fuerte: Optional[dict[str, Any]] = None
    if ordenes_por_dia:
        dia, cantidad = ordenes_por_dia.most_common(1)[0]
        dia_mas_fuerte = {"dia": dia, "ordenes": cantidad}

    ticket_promedio = round(ingreso_total / total_ordenes, 2) if total_ordenes else 0.0

    # Distribuciones completas para las graficas de /reportes
    graficas = {
        "llamadas_por_hora": [llamadas_por_hora.get(h, 0) for h in range(24)],
        "ordenes_por_dia": [{"dia": d, "ordenes": ordenes_por_dia.get(d, 0)} for d in DIAS_SEMANA],
        "platillos_top": [
            {"platillo": p, "cantidad": c, "ingreso": round(platillos_ingreso[p], 2)}
            for p, c in platillos_cantidad.most_common(5)
        ],
    }

    return {
        "graficas": graficas,
        "total_ordenes": total_ordenes,
        "total_llamadas": len(llamadas),
        "ingreso_total": round(ingreso_total, 2),
        "ticket_promedio": ticket_promedio,
        "platillo_top": platillo_top,
        "hora_pico": hora_pico,
        "dia_mas_fuerte": dia_mas_fuerte,
    }
