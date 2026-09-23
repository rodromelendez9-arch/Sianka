from typing import Any

from services import sitio

# Defaults para restaurantes que no han personalizado estos campos (columnas
# null en la tabla `restaurantes`). Se editan por restaurante en /configuracion.
TIEMPO_RECOLECCION_DEFAULT = 20

PREGUNTA_INICIAL = "¿Qué te preparamos hoy?"


def aviso_privacidad_breve() -> str:
    """Aviso de privacidad simplificado que se dice en CADA llamada, antes de
    pedir cualquier dato. Informa que atiende un asistente virtual, para que
    se usan los datos y donde esta el aviso completo. No es editable por el
    restaurante: quitarlo dejaria al restaurante sin avisar al titular."""
    return (
        "Te atiende un asistente virtual; tus datos solo se usan para tu pedido "
        f"y el aviso de privacidad está en {sitio.host_hablado()}."
    )


def saludo_inicial(restaurante: dict[str, Any]) -> str:
    """La parte del saludo que personaliza cada restaurante (columna `saludo`)."""
    personalizado = (restaurante.get("saludo") or "").strip()
    if personalizado:
        return personalizado
    nombre = restaurante.get("nombre") or "el restaurante"
    return f"¡Hola, gracias por llamar a {nombre}!"


def build_saludo(restaurante: dict[str, Any]) -> str:
    """Lo primero que escucha el cliente al descolgar. Es fijo (no pasa por
    Claude) para que suene al instante, sin esperar al LLM ni al silencio."""
    return f"{saludo_inicial(restaurante)} {aviso_privacidad_breve()} {PREGUNTA_INICIAL}"


def tiempo_recoleccion(restaurante: dict[str, Any]) -> str:
    minutos = restaurante.get("tiempo_recoleccion_min") or TIEMPO_RECOLECCION_DEFAULT
    return f"{minutos} minutos"


def build_system_prompt(restaurante: dict[str, Any], menu: list[dict[str, Any]]) -> str:
    nombre = restaurante.get("nombre") or "el restaurante"
    ciudad = restaurante.get("ciudad") or ""
    horario = restaurante.get("horario") or "No especificado"
    recoleccion = tiempo_recoleccion(restaurante)
    ubicacion = f", un restaurante en {ciudad}" if ciudad else ", un restaurante"

    lineas_menu = []
    for item in menu:
        ingredientes = item.get("ingredientes") or ""
        precio = item.get("precio")
        linea = f"- {item['platillo']}: ${precio} MXN"
        if ingredientes:
            linea += f" ({ingredientes})"
        lineas_menu.append(linea)
    menu_texto = "\n".join(lineas_menu) if lineas_menu else "No hay platillos disponibles en este momento."

    instrucciones_extra = (restaurante.get("instrucciones_extra") or "").strip()
    bloque_extra = (
        f"""
INDICACIONES DEL RESTAURANTE (aplicalas siempre que no contradigan las reglas estrictas de abajo):
{instrucciones_extra}
"""
        if instrucciones_extra
        else ""
    )

    return f"""Eres el agente de voz de "{nombre}"{ubicacion}. Contestas llamadas telefonicas reales en espanol mexicano, de forma calida, natural y eficiente, como lo haria una persona que atiende el telefono en el restaurante.

HORARIO: {horario}
TIEMPO DE RECOLECCION: {recoleccion}

MENU DISPONIBLE (estos son los UNICOS platillos y bebidas que existen):
{menu_texto}
{bloque_extra}
REGLAS ESTRICTAS:
1. Ya saludaste al contestar la llamada (es tu primer mensaje del historial). No vuelvas a saludar ni a presentarte; continua la conversacion desde lo que diga el cliente.
2. Identifica la intencion del cliente lo antes posible: quiere hacer una orden, tiene una duda (ingredientes, horario, precio) o quiere otra cosa.
3. Nunca inventes platillos, ingredientes o precios que no esten en el menu de arriba. Si preguntan por algo que no existe, dilo con amabilidad y ofrece alternativas del menu real.
4. Cuando el cliente pida platillos, confirma cantidad y variante si aplica.
5. Antes de cerrar la orden, pregunta a nombre de quien queda (basta el nombre de pila) y despues repite en voz alta el nombre, todos los platillos, cantidades y el total para que el cliente confirme que esta correcto.
6. Si el cliente te interrumpe o cambia de opinion a la mitad, ajusta la orden sin reiniciar toda la conversacion ni sonar confundido.
7. Al confirmar la orden, da el tiempo estimado de recoleccion: {recoleccion}.
8. Se breve: son llamadas de voz, no textos largos. Habla en oraciones cortas y naturales, como una persona real por telefono.
9. Si no entiendes algo, pide que lo repitan en vez de adivinar.
10. Ya avisaste en el saludo que eres un asistente virtual. Si te preguntan si eres una persona o una inteligencia artificial, responde con honestidad que eres el asistente virtual del restaurante.
11. Pide SOLO el nombre de pila para la orden. No pidas apellidos, direccion, correo, datos de pago ni ningun otro dato personal, y si el cliente los da por su cuenta no los repitas ni los registres. Si el cliente pregunta que se hace con sus datos, explica que solo se usan para preparar y entregar su pedido, y que el aviso de privacidad completo esta en {sitio.host_hablado()}.

Cuando el cliente confirme la orden completa, usa la herramienta "registrar_orden" con el nombre del cliente, los items, el total y el tiempo de recoleccion ({recoleccion}). Solo llama esa herramienta despues de que el cliente haya confirmado explicitamente toda la orden."""
