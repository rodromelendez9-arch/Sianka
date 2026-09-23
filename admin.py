"""Administracion de restaurantes de Sianka desde la terminal.

Cada restaurante se identifica por su `slug` (p. ej. "tacos-el-guero"), que
se genera solo a partir del nombre. Ejemplos:

    python admin.py listar
    python admin.py nuevo-restaurante "Tortas La Abuela" --ciudad "Puebla, Puebla" \\
        --horario "Lunes a sabado de 9:00 a 18:00" --twilio +522221234567 --menu menu.csv
    python admin.py nuevo-usuario tortas-la-abuela dueno@tortaslaabuela.mx --nombre "Maria"
    python admin.py importar-menu tortas-la-abuela menu.csv
    python admin.py editar-restaurante tortas-la-abuela --twilio +522229876543
    python admin.py cambiar-password dueno@tortaslaabuela.mx

Proteccion de datos:

    python admin.py generar-clave              # DATA_ENCRYPTION_KEY nueva
    python admin.py cifrar-existentes          # cifra filas previas al cifrado
    python admin.py arco-consultar tacos-el-guero +529991234567 > datos.json
    python admin.py arco-cancelar tacos-el-guero +529991234567
    python admin.py purgar-transcripciones     # aplica la retencion ya

El CSV del menu lleva encabezados: platillo,precio,ingredientes
"""
import argparse
import csv
import getpass
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

from database import supabase_client  # noqa: E402
from services import cifrado_service, sitio  # noqa: E402
from services.auth_service import hashear_password  # noqa: E402

LARGO_MINIMO_PASSWORD = 10


def generar_slug(texto: str) -> str:
    """"Tacos El Güero" -> "tacos-el-guero"."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")


def validar_telefono(numero: str) -> str:
    numero = numero.strip().replace(" ", "")
    if not re.fullmatch(r"\+\d{8,15}", numero):
        sys.exit(f"Numero invalido: {numero!r}. Usa formato internacional, p. ej. +529991234567")
    return numero


def obtener_restaurante(slug: str) -> dict:
    restaurante = supabase_client.get_restaurante_by_slug(slug)
    if not restaurante:
        sys.exit(f"No existe un restaurante con slug {slug!r}. Revisa con: python admin.py listar")
    return restaurante


def pedir_password() -> str:
    while True:
        password = getpass.getpass("Contrasena: ")
        if len(password) < LARGO_MINIMO_PASSWORD:
            print(f"Debe tener al menos {LARGO_MINIMO_PASSWORD} caracteres.")
            continue
        if password != getpass.getpass("Repite la contrasena: "):
            print("No coinciden, intenta de nuevo.")
            continue
        return password


def leer_menu_csv(ruta: str) -> list[dict]:
    platillos = []
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        for numero_linea, fila in enumerate(csv.DictReader(archivo), start=2):
            nombre = (fila.get("platillo") or "").strip()
            if not nombre:
                continue
            try:
                precio = float((fila.get("precio") or "").replace("$", "").strip())
            except ValueError:
                sys.exit(f"{ruta}:{numero_linea}: precio invalido para {nombre!r}")
            platillos.append(
                {"platillo": nombre, "precio": precio, "ingredientes": (fila.get("ingredientes") or "").strip()}
            )
    if not platillos:
        sys.exit(f"{ruta} no tiene platillos. Encabezados esperados: platillo,precio,ingredientes")
    return platillos


def importar_menu(restaurante: dict, ruta: str) -> None:
    existentes = {p["platillo"].lower() for p in supabase_client.get_menu(restaurante["id"])}
    nuevos = 0
    for p in leer_menu_csv(ruta):
        if p["platillo"].lower() in existentes:
            print(f"  = {p['platillo']} (ya existe, se omite)")
            continue
        supabase_client.crear_platillo(restaurante["id"], p["platillo"], p["precio"], p["ingredientes"])
        print(f"  + {p['platillo']}  ${p['precio']:.2f}")
        nuevos += 1
    print(f"{nuevos} platillo(s) agregados al menu de {restaurante['nombre']}.")


# ---------------- Comandos ----------------

def cmd_listar(args) -> None:
    restaurantes = supabase_client.listar_restaurantes()
    if not restaurantes:
        print("No hay restaurantes. Crea uno con: python admin.py nuevo-restaurante \"Nombre\"")
        return
    for r in restaurantes:
        estado = "activo" if r.get("activo") else "INACTIVO"
        print(f"{r['slug']:<28} {r['nombre']:<30} {r.get('twilio_number') or 'sin numero':<16} {estado}")


def cmd_nuevo_restaurante(args) -> None:
    slug = args.slug or generar_slug(args.nombre)
    if not slug:
        sys.exit("No se pudo generar un slug a partir del nombre; pasalo con --slug")
    if supabase_client.get_restaurante_by_slug(slug):
        sys.exit(f"Ya existe un restaurante con slug {slug!r}; elige otro con --slug")

    twilio = validar_telefono(args.twilio) if args.twilio else None
    if twilio and supabase_client.get_restaurante_by_twilio_number(twilio):
        sys.exit(f"El numero {twilio} ya esta asignado a otro restaurante")

    restaurante = supabase_client.crear_restaurante(
        slug=slug,
        nombre=args.nombre,
        ciudad=args.ciudad,
        horario=args.horario,
        twilio_number=twilio,
        activo=True,
    )
    print(f"Restaurante creado: {restaurante['nombre']} (slug: {slug})")

    if args.menu:
        importar_menu(restaurante, args.menu)
    if not twilio:
        print(f"Aun no recibe llamadas: asigna su numero con\n  python admin.py editar-restaurante {slug} --twilio +52...")
    print(f"Siguiente paso: python admin.py nuevo-usuario {slug} correo@ejemplo.com")


def cmd_editar_restaurante(args) -> None:
    restaurante = obtener_restaurante(args.slug)
    campos = {}
    if args.nombre:
        campos["nombre"] = args.nombre
    if args.ciudad is not None:
        campos["ciudad"] = args.ciudad
    if args.horario is not None:
        campos["horario"] = args.horario
    if args.voz is not None:
        campos["voz_tts"] = args.voz or None
    if args.twilio is not None:
        twilio = validar_telefono(args.twilio) if args.twilio else None
        otro = supabase_client.get_restaurante_by_twilio_number(twilio) if twilio else None
        if otro and otro["id"] != restaurante["id"]:
            sys.exit(f"El numero {twilio} ya esta asignado a {otro['slug']}")
        campos["twilio_number"] = twilio
    for campo in ("razon_social", "domicilio", "email_privacidad"):
        valor = getattr(args, campo)
        if valor is not None:
            campos[campo] = valor.strip() or None
    if args.activo is not None:
        campos["activo"] = args.activo

    if not campos:
        sys.exit("Nada que cambiar. Usa --help para ver las opciones.")
    supabase_client.actualizar_restaurante(restaurante["id"], **campos)
    print(f"{restaurante['slug']} actualizado: {', '.join(campos)}")


def cmd_nuevo_usuario(args) -> None:
    restaurante = obtener_restaurante(args.slug)
    email = args.email.strip().lower()
    if supabase_client.get_usuario_por_email(email):
        sys.exit(f"Ya existe un usuario con el correo {email}")
    password = pedir_password()
    supabase_client.crear_usuario(restaurante["id"], email, hashear_password(password), args.nombre or "")
    print(f"Usuario {email} creado para {restaurante['nombre']}. Ya puede entrar en /login")


def cmd_cambiar_password(args) -> None:
    if not supabase_client.get_usuario_por_email(args.email):
        sys.exit(f"No existe un usuario activo con el correo {args.email}")
    supabase_client.actualizar_password_usuario(args.email, hashear_password(pedir_password()))
    print("Contrasena actualizada.")


def cmd_importar_menu(args) -> None:
    importar_menu(obtener_restaurante(args.slug), args.archivo)


def cmd_generar_clave(args) -> None:
    print(cifrado_service.generar_clave())
    print(
        "\nGuardala en .env como DATA_ENCRYPTION_KEY=... y RESPALDALA fuera del servidor.\n"
        "Si se pierde, los datos cifrados (telefonos, nombres, transcripciones) son irrecuperables.\n"
        "No la cambies una vez que haya datos cifrados con ella.",
        file=sys.stderr,
    )


def cmd_cifrar_existentes(args) -> None:
    conteo = supabase_client.cifrar_filas_existentes()
    print(f"Cifradas: {conteo['llamadas']} llamada(s) y {conteo['ordenes']} orden(es).")


def cmd_arco_consultar(args) -> None:
    """Derecho de ACCESO: imprime en JSON todo lo que hay de ese numero en
    ese restaurante, para entregarselo al titular."""
    restaurante = obtener_restaurante(args.slug)
    llamadas = supabase_client.get_llamadas_por_telefono(restaurante["id"], args.telefono)
    if not llamadas:
        print(f"No hay datos de {args.telefono} en {restaurante['nombre']}.", file=sys.stderr)
        return
    for llamada in llamadas:
        llamada.pop("telefono_hash", None)
    print(json.dumps({"restaurante": restaurante["nombre"], "llamadas": llamadas}, ensure_ascii=False, indent=2, default=str))


def cmd_arco_cancelar(args) -> None:
    """Derecho de CANCELACION: borra telefono, nombre y transcripciones. Los
    pedidos quedan sin datos personales (el restaurante los necesita para su
    contabilidad)."""
    restaurante = obtener_restaurante(args.slug)
    llamadas = supabase_client.get_llamadas_por_telefono(restaurante["id"], args.telefono)
    if not llamadas:
        print(f"No hay datos de {args.telefono} en {restaurante['nombre']}.")
        return
    if not args.si:
        respuesta = input(
            f"Se anonimizaran {len(llamadas)} llamada(s) de {args.telefono} en {restaurante['nombre']}. "
            "Esto no se puede deshacer. Escribe 'si' para continuar: "
        )
        if respuesta.strip().lower() != "si":
            sys.exit("Cancelado.")
    total = supabase_client.anonimizar_cliente(restaurante["id"], args.telefono)
    print(f"Listo: {total} llamada(s) anonimizadas. Responde al titular confirmando la cancelacion.")


def cmd_purgar_transcripciones(args) -> None:
    dias = args.dias if args.dias is not None else sitio.RETENCION_TRANSCRIPCIONES_DIAS
    limite = datetime.now(timezone.utc) - timedelta(days=dias)
    print(f"{supabase_client.purgar_transcripciones(limite.isoformat())} transcripcion(es) borradas (mas de {dias} dias).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Administracion de restaurantes de Sianka")
    sub = parser.add_subparsers(dest="comando", required=True)

    sub.add_parser("listar", help="Lista los restaurantes").set_defaults(func=cmd_listar)

    p = sub.add_parser("nuevo-restaurante", help="Da de alta un restaurante")
    p.add_argument("nombre")
    p.add_argument("--slug", help="Identificador; por defecto se genera del nombre")
    p.add_argument("--ciudad")
    p.add_argument("--horario")
    p.add_argument("--twilio", help="Numero de Twilio que contesta sus llamadas (+52...)")
    p.add_argument("--menu", help="CSV con columnas platillo,precio,ingredientes")
    p.set_defaults(func=cmd_nuevo_restaurante)

    p = sub.add_parser("editar-restaurante", help="Cambia datos de un restaurante")
    p.add_argument("slug")
    p.add_argument("--nombre")
    p.add_argument("--ciudad")
    p.add_argument("--horario")
    p.add_argument("--twilio", help='Numero de Twilio; "" para quitarlo')
    p.add_argument("--voz", help='Voz de Deepgram Aura (p. ej. aura-2-celeste-es); "" para usar la default')
    p.add_argument("--razon-social", dest="razon_social")
    p.add_argument("--domicilio")
    p.add_argument("--email-privacidad", dest="email_privacidad")
    p.add_argument("--activo", dest="activo", action="store_true", default=None)
    p.add_argument("--inactivo", dest="activo", action="store_false")
    p.set_defaults(func=cmd_editar_restaurante)

    p = sub.add_parser("nuevo-usuario", help="Crea un acceso al dashboard para un restaurante")
    p.add_argument("slug")
    p.add_argument("email")
    p.add_argument("--nombre")
    p.set_defaults(func=cmd_nuevo_usuario)

    p = sub.add_parser("cambiar-password", help="Cambia la contrasena de un usuario")
    p.add_argument("email")
    p.set_defaults(func=cmd_cambiar_password)

    p = sub.add_parser("importar-menu", help="Agrega platillos desde un CSV")
    p.add_argument("slug")
    p.add_argument("archivo")
    p.set_defaults(func=cmd_importar_menu)

    sub.add_parser("generar-clave", help="Genera una DATA_ENCRYPTION_KEY").set_defaults(func=cmd_generar_clave)
    sub.add_parser(
        "cifrar-existentes", help="Cifra datos personales guardados antes del cifrado"
    ).set_defaults(func=cmd_cifrar_existentes)

    p = sub.add_parser("arco-consultar", help="Derecho de acceso: exporta los datos de un numero (JSON)")
    p.add_argument("slug")
    p.add_argument("telefono")
    p.set_defaults(func=cmd_arco_consultar)

    p = sub.add_parser("arco-cancelar", help="Derecho de cancelacion: anonimiza los datos de un numero")
    p.add_argument("slug")
    p.add_argument("telefono")
    p.add_argument("--si", action="store_true", help="No pedir confirmacion")
    p.set_defaults(func=cmd_arco_cancelar)

    p = sub.add_parser("purgar-transcripciones", help="Borra transcripciones mas viejas que la retencion")
    p.add_argument("--dias", type=int, help=f"Default: {sitio.RETENCION_TRANSCRIPCIONES_DIAS}")
    p.set_defaults(func=cmd_purgar_transcripciones)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
