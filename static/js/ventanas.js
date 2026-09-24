/* Gestor de ventanas del centro de mando.
 *
 * Cada .ventana del #escritorio se puede arrastrar (por su barra), cambiar de
 * tamano (esquina inferior derecha), minimizar, maximizar (doble clic o boton)
 * y mover con el teclado (flechas; Shift+flechas cambia el tamano). El acomodo
 * se guarda en localStorage por navegador.
 *
 * Posiciones: x y w en % del ancho del escritorio (asi el acomodo se adapta al
 * ancho de la pantalla); y y h en px. En pantallas angostas las ventanas se
 * apilan y se desactiva el arrastre.
 */
(function () {
  const CLAVE = "sianka.ventanas.v1";
  const MARGEN = 8; // px de separacion entre ventanas
  const REJILLA_Y = 8; // las ventanas "caen" en multiplos de 8px
  const MIN_W = 18; // %
  const MIN_H = 150; // px
  const ANCHO_APILADO = 1000;

  // Acomodo inicial: arriba la llamada y el resumen, abajo los pedidos con
  // entregas y menu a la derecha.
  const ACOMODO_BASE = {
    llamada: { x: 0, y: 0, w: 38, h: 340 },
    hoy: { x: 38, y: 0, w: 62, h: 340 },
    pedidos: { x: 0, y: 356, w: 64, h: 600 },
    entregas: { x: 64, y: 356, w: 36, h: 330 },
    menu: { x: 64, y: 702, w: 36, h: 254 },
  };

  const escritorio = document.getElementById("escritorio");
  if (!escritorio) return;

  const ventanas = [...escritorio.querySelectorAll(".ventana")];
  let acomodo = cargar();
  let zSiguiente = 10;

  function cargar() {
    try {
      const guardado = JSON.parse(localStorage.getItem(CLAVE) || "null");
      if (guardado && typeof guardado === "object") {
        return Object.fromEntries(
          Object.entries(ACOMODO_BASE).map(([id, base]) => [id, { ...base, ...(guardado[id] || {}) }])
        );
      }
    } catch (error) {
      /* localStorage puede no estar disponible (modo privado): se usa el acomodo base */
    }
    return structuredClone(ACOMODO_BASE);
  }

  function guardar() {
    try {
      localStorage.setItem(CLAVE, JSON.stringify(acomodo));
    } catch (error) {
      /* sin almacenamiento: el acomodo vive solo en esta pestana */
    }
  }

  const apilado = () => window.innerWidth < ANCHO_APILADO;
  const idDe = (ventana) => ventana.dataset.ventana;

  function aplicar(ventana) {
    const a = acomodo[idDe(ventana)];
    if (!a) return;
    ventana.classList.toggle("minimizada", !!a.minimizada);
    if (apilado()) return;

    if (a.maximizada) {
      ventana.style.left = `${MARGEN / 2}px`;
      ventana.style.top = "0px";
      ventana.style.width = `calc(100% - ${MARGEN}px)`;
      ventana.style.height = `${Math.max(window.innerHeight - 170, 400)}px`;
      ventana.style.zIndex = 50;
      return;
    }
    ventana.style.left = `calc(${a.x}% + ${MARGEN / 2}px)`;
    ventana.style.top = `${a.y}px`;
    ventana.style.width = `calc(${a.w}% - ${MARGEN}px)`;
    ventana.style.height = `${a.h}px`;
  }

  function ajustarAltoEscritorio() {
    if (apilado()) {
      escritorio.style.height = "";
      return;
    }
    const fondo = ventanas.reduce((max, v) => Math.max(max, v.offsetTop + v.offsetHeight), 0);
    escritorio.style.height = `${fondo + 24}px`;
  }

  function aplicarTodo() {
    escritorio.classList.toggle("apilado", apilado());
    ventanas.forEach(aplicar);
    ajustarAltoEscritorio();
  }

  function enfocar(ventana) {
    ventanas.forEach((v) => v.classList.remove("enfocada"));
    ventana.classList.add("enfocada");
    if (!acomodo[idDe(ventana)]?.maximizada) ventana.style.zIndex = ++zSiguiente;
  }

  const limitar = (valor, min, max) => Math.min(Math.max(valor, min), max);

  // ---------------- Arrastrar y redimensionar ----------------

  function iniciarGesto(evento, ventana, tipo) {
    if (apilado() || evento.button > 0) return;
    const a = acomodo[idDe(ventana)];
    if (a.maximizada && tipo === "redimensionar") return;

    evento.preventDefault();
    enfocar(ventana);
    if (a.maximizada) {
      // Arrastrar una ventana maximizada la "despega" a su tamano normal
      a.maximizada = false;
      aplicar(ventana);
    }

    const ancho = escritorio.clientWidth;
    const inicio = { px: evento.clientX, py: evento.clientY, ...a };
    const clase = tipo === "mover" ? "arrastrando" : "redimensionando";
    ventana.classList.add(clase);
    evento.target.setPointerCapture(evento.pointerId);

    function mover(e) {
      const dx = ((e.clientX - inicio.px) / ancho) * 100;
      const dy = e.clientY - inicio.py;
      if (tipo === "mover") {
        a.x = limitar(inicio.x + dx, 0, 100 - a.w);
        a.y = Math.max(0, inicio.y + dy);
      } else {
        a.w = limitar(inicio.w + dx, MIN_W, 100 - a.x);
        a.h = Math.max(MIN_H, inicio.h + dy);
      }
      aplicar(ventana);
      ajustarAltoEscritorio();
    }

    function soltar() {
      a.x = Math.round(a.x * 2) / 2;
      a.y = Math.round(a.y / REJILLA_Y) * REJILLA_Y;
      a.w = Math.round(a.w * 2) / 2;
      a.h = Math.round(a.h / REJILLA_Y) * REJILLA_Y;
      ventana.classList.remove(clase);
      aplicar(ventana);
      ajustarAltoEscritorio();
      guardar();
      evento.target.removeEventListener("pointermove", mover);
      evento.target.removeEventListener("pointerup", soltar);
      evento.target.removeEventListener("pointercancel", soltar);
    }

    evento.target.addEventListener("pointermove", mover);
    evento.target.addEventListener("pointerup", soltar);
    evento.target.addEventListener("pointercancel", soltar);
  }

  function alternar(ventana, propiedad) {
    const a = acomodo[idDe(ventana)];
    a[propiedad] = !a[propiedad];
    if (propiedad === "maximizada" && a.maximizada) a.minimizada = false;
    if (!a.maximizada) ventana.style.zIndex = ++zSiguiente;
    aplicar(ventana);
    ajustarAltoEscritorio();
    guardar();
  }

  // ---------------- Teclado ----------------

  function teclado(evento, ventana) {
    const pasos = { ArrowLeft: [-2, 0], ArrowRight: [2, 0], ArrowUp: [0, -24], ArrowDown: [0, 24] };
    const paso = pasos[evento.key];
    if (!paso || apilado()) return;
    evento.preventDefault();
    const a = acomodo[idDe(ventana)];
    if (evento.shiftKey) {
      a.w = limitar(a.w + paso[0], MIN_W, 100 - a.x);
      a.h = Math.max(MIN_H, a.h + paso[1]);
    } else {
      a.x = limitar(a.x + paso[0], 0, 100 - a.w);
      a.y = Math.max(0, a.y + paso[1]);
    }
    aplicar(ventana);
    ajustarAltoEscritorio();
    guardar();
  }

  // ---------------- Conexion de eventos ----------------

  ventanas.forEach((ventana) => {
    const barra = ventana.querySelector(".ventana-barra");
    const esquina = ventana.querySelector(".ventana-redimensionar");

    ventana.addEventListener("pointerdown", () => enfocar(ventana));
    barra.addEventListener("pointerdown", (e) => {
      if (e.target.closest("button")) return;
      iniciarGesto(e, ventana, "mover");
    });
    barra.addEventListener("dblclick", (e) => {
      if (!e.target.closest("button") && !apilado()) alternar(ventana, "maximizada");
    });
    barra.addEventListener("keydown", (e) => teclado(e, ventana));
    esquina?.addEventListener("pointerdown", (e) => iniciarGesto(e, ventana, "redimensionar"));
    ventana.querySelector("[data-minimizar]")?.addEventListener("click", () => alternar(ventana, "minimizada"));
    ventana.querySelector("[data-maximizar]")?.addEventListener("click", () => alternar(ventana, "maximizada"));
  });

  document.querySelector("[data-reacomodar]")?.addEventListener("click", () => {
    acomodo = structuredClone(ACOMODO_BASE);
    guardar();
    ventanas.forEach((v) => (v.style.zIndex = ""));
    aplicarTodo();
  });

  // Las ventanas tienen alto fijo (su contenido hace scroll), asi que el alto
  // del escritorio solo cambia al mover, redimensionar o cambiar el ancho.
  window.addEventListener("resize", aplicarTodo);
  aplicarTodo();
})();
