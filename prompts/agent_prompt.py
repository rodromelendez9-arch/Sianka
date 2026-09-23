from typing import Any

from services import sitio

# Defaults para restaurantes que no han personalizado estos campos (columnas
# null en la tabla `restaurantes`). Se editan por restaurante en /configuracion.
TIEMPO_RECOLECCION_DEFAULT = 20
TIEMPO_ENTREGA_DEFAULT = 45

PREGUNTA_INICIAL = "¿Qué te preparamos hoy?"


def url_aviso_privacidad(restaurante: dict[str, Any]) -> str:
    """El aviso del restaurante: el de su propio sitio si lo tiene (asi no se
    menciona la plataforma), o el que Sianka publica por el."""
    propio = (restaurante.get("url_aviso_privacidad") or "").strip()
    return propio or sitio.url(f"/privacidad/{restaurante.get('slug', '')}")


def aviso_privacidad_breve(restaurante: dict[str, Any]) -> str:
    """Frase opcional (columna `aviso_en_llamada`) que se dice en el saludo.
    Neutral: no menciona tecnologia ni proveedores."""
    return (
        "Tus datos solo se usan para atender tu pedido; nuestro aviso de privacidad "
        f"está en {sitio.url_hablada(url_aviso_privacidad(restaurante))}."
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
    partes = [saludo_inicial(restaurante)]
    if restaurante.get("aviso_en_llamada"):
        partes.append(aviso_privacidad_breve(restaurante))
    partes.append(PREGUNTA_INICIAL)
    return " ".join(partes)


def tiempo_recoleccion(restaurante: dict[str, Any]) -> str:
    minutos = restaurante.get("tiempo_recoleccion_min") or TIEMPO_RECOLECCION_DEFAULT
    return f"{minutos} minutos"


def tiempo_entrega(restaurante: dict[str, Any]) -> str:
    minutos = restaurante.get("tiempo_entrega_min") or TIEMPO_ENTREGA_DEFAULT
    return f"{minutos} minutos"


def _pesos(valor: Any) -> str:
    return f"${float(valor or 0):.2f} MXN"


def _bloque_entregas(restaurante: dict[str, Any], numero_visible: bool) -> str:
    if not restaurante.get("ofrece_entregas"):
        return """
ENTREGAS: este restaurante SOLO maneja pedidos para recoger en el local. Si el cliente pide envio a domicilio, dile con amabilidad que por ahora solo es para recoger.
"""

    zona = (restaurante.get("zona_entrega") or "").strip() or "No especificada: acepta cualquier direccion de la ciudad."
    minimo = float(restaurante.get("pedido_minimo_envio") or 0)
    linea_minimo = f"Pedido minimo para envio (sin contar el envio): {_pesos(minimo)}." if minimo > 0 else "No hay pedido minimo para envio."
    linea_telefono = (
        "El numero desde el que llama el cliente ya queda registrado para el repartidor; NO se lo pidas, salvo que el cliente quiera dar otro."
        if numero_visible
        else "El cliente llama desde un numero PRIVADO: si pide a domicilio, pidele un telefono de contacto para el repartidor."
    )
    return f"""
ENTREGAS A DOMICILIO (el restaurante tambien las ofrece):
- Costo de envio: {_pesos(restaurante.get('costo_envio'))}. Se suma al total.
- {linea_minimo}
- Tiempo estimado de entrega: {tiempo_entrega(restaurante)}.
- Zona de entrega: {zona}
- Si la direccion claramente esta fuera de la zona, dilo con amabilidad y ofrece que pase a recoger.
- Para envio pide: calle, numero, colonia y referencias (entre que calles, color de fachada). Confirma la direccion repitiendola.
- Pregunta si paga en efectivo o con tarjeta al recibir; si es efectivo, pregunta con cuanto paga para llevar cambio.
- {linea_telefono}
"""


def build_system_prompt(
    restaurante: dict[str, Any],
    menu: list[dict[str, Any]],
    numero_visible: bool = True,
) -> str:
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

    return f"""Eres quien atiende el telefono de "{nombre}"{ubicacion}. Contestas llamadas telefonicas reales en espanol mexicano, de forma calida, natural y eficiente, como lo haria una persona del restaurante.

HORARIO: {horario}
TIEMPO DE RECOLECCION EN EL LOCAL: {recoleccion}

MENU DISPONIBLE (estos son los UNICOS platillos y bebidas que existen):
{menu_texto}
{_bloque_entregas(restaurante, numero_visible)}{bloque_extra}
REGLAS ESTRICTAS:
1. Ya saludaste al contestar la llamada (es tu primer mensaje del historial). No vuelvas a saludar ni a presentarte; continua la conversacion desde lo que diga el cliente.
2. Identifica la intencion del cliente lo antes posible: quiere hacer una orden, tiene una duda (ingredientes, horario, precio) o quiere otra cosa.
3. Nunca inventes platillos, ingredientes o precios que no esten en el menu de arriba. Si preguntan por algo que no existe, dilo con amabilidad y ofrece alternativas del menu real.
4. Cuando el cliente pida platillos, confirma cantidad y variante si aplica.
5. Antes de cerrar la orden: pregunta a nombre de quien queda (basta el nombre de pila) y si pasa a recoger o es a domicilio (si hay envio). Despues repite en voz alta el nombre, los platillos, las cantidades y, si es a domicilio, la direccion, para que el cliente confirme.
6. Si el cliente te interrumpe o cambia de opinion a la mitad, ajusta la orden sin reiniciar toda la conversacion ni sonar confundido.
7. Se breve: son llamadas de voz, no textos largos. Habla en oraciones cortas y naturales, como una persona real por telefono.
8. Si no entiendes algo, pide que lo repitan en vez de adivinar. Con las direcciones, si dudas de un nombre de calle o colonia, pide que lo deletreen.
9. No menciones que eres un asistente virtual ni hables de tecnologia, sistemas o empresas que usa el restaurante. Si el cliente te pregunta directamente si eres una persona o una maquina, no afirmes ser una persona: responde en una frase que eres el asistente de pedidos de {nombre} y continua con el pedido, sin dar mas detalles.
10. Pide SOLO los datos necesarios para el pedido: nombre de pila y, si es a domicilio, direccion, referencias, forma de pago y con cuanto paga. Nunca pidas apellidos, correo, numeros de tarjeta ni otros datos. Si el cliente pregunta que se hace con sus datos, explica que solo se usan para atender su pedido y que el aviso de privacidad esta en {sitio.url_hablada(url_aviso_privacidad(restaurante))}.

REGISTRO DE LA ORDEN:
- Cuando el cliente confirme la orden completa, llama la herramienta "registrar_orden" SIN decir nada en ese mismo mensaje.
- La herramienta te devuelve el resultado. Si se registro, confirma al cliente el total final que te indica (incluye el envio si aplica) y el tiempo estimado, y despidete. Si NO se registro, explica con amabilidad el motivo que te indica y ayuda a corregirlo; no digas que el pedido quedo registrado."""
