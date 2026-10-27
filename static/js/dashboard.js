/* Panel del restaurante: eventos en vivo (WebSocket) y centro de mando.
 * Se carga en todas las paginas del panel (templates/base.html); las partes
 * del centro de mando solo actuan si sus elementos existen en la pagina.
 */
(function () {
  const ESTADOS = ["nueva", "confirmada", "preparando", "lista", "entregada"];

  const ESTADO_LABELS = {
    nueva: "Nueva",
    confirmada: "Confirmada",
    preparando: "Preparando",
    lista: "Lista",
    entregada: "Entregada",
  };

  const ACCIONES_POR_ESTADO = {
    nueva: [
      { label: "Confirmar ✓", siguiente: "confirmada", clase: "btn-primary" },
      { label: "✕", siguiente: "entregada", clase: "btn-danger" },
    ],
    confirmada: [{ label: "Iniciar preparacion", siguiente: "preparando", clase: "btn-primary" }],
    preparando: [{ label: "Lista para recoger", siguiente: "lista", clase: "btn-primary" }],
    lista: [{ label: "Marcar entregada", siguiente: "entregada", clase: "btn-primary" }],
    entregada: [],
  };

  // En pedidos a domicilio, pasar de "preparando" a "lista" significa que
  // sale a entregarse. Clave: "estadoActual>siguiente" (asi el boton ✕ de una
  // orden nueva, que tambien lleva a "entregada", no cambia de etiqueta).
  const ETIQUETAS_DOMICILIO = {
    "preparando>lista": "Salio a entregar",
  };

  let llamadaInicioTimestamp = null;
  let timerInterval = null;

  const $ = (id) => document.getElementById(id);

  function elemento(tag, clase, texto) {
    const el = document.createElement(tag);
    if (clase) el.className = clase;
    if (texto !== undefined) el.textContent = texto;
    return el;
  }

  const pesos = (valor) => `$${Number(valor || 0).toFixed(2)}`;
  const pesosMiles = (valor) =>
    `$${Number(valor || 0).toLocaleString("es-MX", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  // ---------------- WebSocket ----------------

  function conectarWebSocket() {
    const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocolo}//${location.host}/ws/dashboard`);

    socket.addEventListener("message", (evento) => {
      let data;
      try {
        data = JSON.parse(evento.data);
      } catch (error) {
        return;
      }
      manejarEvento(data);
    });

    socket.addEventListener("close", () => setTimeout(conectarWebSocket, 3000));
    return socket;
  }

  function manejarEvento(data) {
    switch (data.evento) {
      case "llamada_activa":
        mostrarLlamadaActiva(data);
        break;
      case "transcripcion":
        actualizarTranscripcion(data);
        break;
      case "orden_nueva":
        agregarOrdenNueva(data);
        registrarPedidoNuevo(data.orden_id);
        break;
      case "orden_actualizada":
        actualizarStatusOrden(data);
        registrarCambioDePedido(data.orden_id, data.status);
        break;
      case "llamada_terminada":
        ocultarLlamadaActiva();
        break;
      default:
        break;
    }
  }

  // ---------------- Llamada en vivo ----------------

  function ventanaLlamada() {
    return document.querySelector('.ventana[data-ventana="llamada"]');
  }

  function mostrarLlamadaActiva(data) {
    const contenedor = $("llamada-activa");
    if (!contenedor) return;

    contenedor.classList.remove("oculto");
    $("llamada-espera")?.classList.add("oculto");
    ventanaLlamada()?.classList.add("en-vivo");

    $("llamada-telefono").textContent = data.telefono_cliente || "Desconocido";
    $("llamada-transcripcion").replaceChildren();
    $("llamada-estado").textContent = "Identificando intencion";

    llamadaInicioTimestamp = Date.now();
    iniciarTimer();
  }

  function ocultarLlamadaActiva() {
    $("llamada-activa")?.classList.add("oculto");
    $("llamada-espera")?.classList.remove("oculto");
    ventanaLlamada()?.classList.remove("en-vivo");
    detenerTimer();
  }

  function iniciarTimer() {
    detenerTimer();
    const timerEl = $("llamada-timer");
    if (!timerEl) return;
    timerInterval = setInterval(() => {
      const segundos = Math.floor((Date.now() - llamadaInicioTimestamp) / 1000);
      timerEl.textContent = `${String(Math.floor(segundos / 60)).padStart(2, "0")}:${String(segundos % 60).padStart(2, "0")}`;
    }, 1000);
  }

  function detenerTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function actualizarTranscripcion(data) {
    const contenedor = $("llamada-transcripcion");
    if (!contenedor) return;

    const esAgente = data.hablante === "agente";
    // Lo que dice el cliente llega por fragmentos provisionales: se actualiza
    // una sola burbuja hasta que Deepgram manda la version final.
    let linea = !esAgente ? contenedor.querySelector(".linea.provisional") : null;
    if (!linea) {
      linea = elemento("div", `linea ${esAgente ? "agente" : "cliente"}`);
      linea.append(elemento("span", "hablante", esAgente ? "Agente" : "Cliente"), document.createTextNode(""));
      contenedor.appendChild(linea);
    }
    linea.lastChild.textContent = data.texto || "";
    linea.classList.toggle("provisional", !esAgente && data.es_final === false);
    contenedor.scrollTop = contenedor.scrollHeight;

    if (!esAgente) $("llamada-estado").textContent = "Tomando orden";
  }

  // ---------------- Tarjetas de orden ----------------

  function etiquetaNumero(orden) {
    if (orden.numero_dia) return String(orden.numero_dia).padStart(3, "0");
    return `#${(orden.orden_id || "").slice(0, 8)}`;
  }

  function textoPago(orden) {
    if (orden.metodo_pago === "efectivo") {
      return orden.paga_con
        ? `Paga en efectivo con ${pesos(orden.paga_con)} · cambio ${pesos(orden.paga_con - orden.total)}`
        : "Paga en efectivo";
    }
    return orden.metodo_pago === "tarjeta" ? "Paga con tarjeta (llevar terminal)" : "";
  }

  function lineaItem(etiqueta, monto, cantidad, claseExtra) {
    const linea = elemento("div", `orden-item${claseExtra ? ` ${claseExtra}` : ""}`);
    const nombre = elemento("span");
    if (cantidad !== undefined) nombre.appendChild(elemento("span", "cantidad", `${cantidad}x`));
    nombre.appendChild(document.createTextNode(etiqueta || ""));
    linea.append(nombre, elemento("span", undefined, pesos(monto)));
    return linea;
  }

  function crearTarjetaOrden(orden) {
    const aDomicilio = orden.tipo_entrega === "domicilio";
    const numero = etiquetaNumero(orden);
    const pago = textoPago(orden);

    const card = elemento("article", "orden-card");
    Object.assign(card.dataset, {
      ordenId: orden.orden_id,
      status: orden.status || "nueva",
      tipo: aDomicilio ? "domicilio" : "recoger",
      numero,
      nombre: orden.nombre_cliente || "",
      direccion: orden.direccion_entrega || "",
      referencias: orden.referencias_entrega || "",
      telefono: orden.telefono_contacto || "",
      pago,
      created: orden.timestamp || new Date().toISOString(),
    });

    const header = elemento("div", "orden-card-header");
    const etiqueta = elemento("span", "orden-numero", "Orden ");
    etiqueta.appendChild(elemento("strong", undefined, numero));
    const tiempo = elemento("span", "orden-tiempo-transcurrido", "hace un momento");
    tiempo.dataset.created = card.dataset.created;
    header.append(etiqueta, tiempo);
    card.appendChild(header);

    const fotos = elemento("div", "orden-fotos");
    fotos.setAttribute("aria-hidden", "true");
    (orden.items || []).slice(0, 4).forEach((item) => {
      const img = elemento("img");
      img.src = item.ilustracion || "/static/img/platillos/plato.svg";
      img.alt = "";
      fotos.appendChild(img);
    });
    card.appendChild(fotos);

    if (orden.nombre_cliente) card.appendChild(elemento("div", "orden-cliente", orden.nombre_cliente));

    const pills = elemento("div", "orden-pills");
    pills.append(
      elemento("span", `status-pill status-${card.dataset.status}`, ESTADO_LABELS[card.dataset.status] || card.dataset.status),
      elemento("span", `tipo-pill tipo-${card.dataset.tipo}`, aDomicilio ? "A domicilio" : "Para recoger")
    );
    card.appendChild(pills);

    const items = elemento("div", "orden-items");
    (orden.items || []).forEach((item) => items.appendChild(lineaItem(item.platillo, item.subtotal, item.cantidad)));
    if (aDomicilio && Number(orden.costo_envio) > 0) {
      items.appendChild(lineaItem("Envio", orden.costo_envio, undefined, "orden-item-envio"));
    }
    card.appendChild(items);

    const total = elemento("div", "orden-total");
    total.append(elemento("span", undefined, "Total"), elemento("span", undefined, pesos(orden.total)));
    card.appendChild(total);

    if (aDomicilio) {
      const bloque = elemento("div", "orden-entrega");
      bloque.appendChild(elemento("div", "orden-entrega-direccion", orden.direccion_entrega || "Direccion no disponible"));
      if (orden.referencias_entrega) bloque.appendChild(elemento("div", "orden-entrega-detalle", orden.referencias_entrega));
      if (orden.telefono_contacto) {
        const tel = elemento("a", "orden-entrega-telefono", orden.telefono_contacto);
        tel.href = `tel:${orden.telefono_contacto}`;
        bloque.appendChild(tel);
      }
      if (pago) bloque.appendChild(elemento("div", "orden-entrega-detalle", pago));
      card.appendChild(bloque);
    }

    card.appendChild(elemento("div", "orden-recoleccion", `${aDomicilio ? "Entrega" : "Recoleccion"}: ${orden.recoleccion || ""}`));
    const acciones = elemento("div", "orden-acciones");
    acciones.setAttribute("data-acciones", "");
    card.appendChild(acciones);

    renderAccionesOrden(card, card.dataset.status);
    return card;
  }

  function agregarOrdenNueva(data) {
    const grid = $("grid-ordenes");
    if (!grid) return;
    grid.querySelector(".estado-vacio")?.remove();

    const card = crearTarjetaOrden(data);
    card.classList.add("recien-llegada");
    grid.prepend(card);

    actualizarPipelineDesdeDOM();
    renderEntregas();
    sumarAlResumen(data);
  }

  function actualizarStatusOrden(data) {
    const card = document.querySelector(`.orden-card[data-orden-id="${data.orden_id}"]`);
    if (!card) return;

    card.dataset.status = data.status;
    const pill = card.querySelector(".status-pill");
    if (pill) {
      pill.className = `status-pill status-${data.status}`;
      pill.textContent = ESTADO_LABELS[data.status] || data.status;
    }

    if (data.status === "entregada") card.remove();
    else renderAccionesOrden(card, data.status);

    actualizarPipelineDesdeDOM();
    renderEntregas();
  }

  function renderAccionesOrden(card, status) {
    const acciones = card.querySelector("[data-acciones]");
    if (!acciones) return;

    acciones.replaceChildren();
    const definiciones = (ACCIONES_POR_ESTADO[status] || []).map((accion) =>
      card.dataset.tipo === "domicilio" && ETIQUETAS_DOMICILIO[`${status}>${accion.siguiente}`]
        ? { ...accion, label: ETIQUETAS_DOMICILIO[`${status}>${accion.siguiente}`] }
        : accion
    );

    definiciones.forEach((accion) => {
      const boton = elemento("button", `btn ${accion.clase}`, accion.label);
      boton.type = "button";
      boton.addEventListener("click", () => cambiarStatusOrden(card.dataset.ordenId, accion.siguiente));
      acciones.appendChild(boton);
    });
  }

  async function cambiarStatusOrden(ordenId, nuevoStatus) {
    try {
      const respuesta = await fetch(`/api/ordenes/${ordenId}/status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nuevoStatus }),
      });
      if (!respuesta.ok) {
        alert("No se pudo actualizar el estatus de la orden.");
        return;
      }
      actualizarStatusOrden({ orden_id: ordenId, status: nuevoStatus });
    } catch (error) {
      alert("Error de conexion al actualizar la orden.");
    }
  }

  function actualizarPipelineDesdeDOM() {
    const conteos = Object.fromEntries(ESTADOS.map((s) => [s, 0]));
    const cards = document.querySelectorAll(".orden-card");
    cards.forEach((card) => {
      if (conteos[card.dataset.status] !== undefined) conteos[card.dataset.status] += 1;
    });

    ESTADOS.forEach((status) => {
      const numeroEl = $(`pipeline-count-${status}`);
      if (numeroEl) numeroEl.textContent = conteos[status];
      $(`pipeline-${status}`)?.classList.toggle("activa", conteos[status] > 0);
    });

    const dato = document.querySelector("[data-dato-pedidos]");
    if (dato) dato.textContent = `${cards.length} activos`;
  }

  function actualizarTiemposTranscurridos() {
    document.querySelectorAll(".orden-tiempo-transcurrido[data-created]").forEach((el) => {
      const creado = new Date(el.dataset.created).getTime();
      if (Number.isNaN(creado)) return;
      const minutos = Math.floor((Date.now() - creado) / 60000);
      el.textContent = minutos <= 0 ? "hace un momento" : `hace ${minutos} min`;
    });
  }

  // ---------------- Ventana "Hoy" ----------------

  let ordenesPorHora = null;

  function dibujarGraficaHoy() {
    const contenedor = $("grafica-hoy");
    if (!contenedor || !window.Graficas || !ordenesPorHora) return;
    // Ultimas 12 horas hasta la hora actual (el resto del dia aun no pasa)
    const horaActual = new Date().getHours();
    const desde = Math.max(0, horaActual - 11);
    const valores = ordenesPorHora.slice(desde, horaActual + 1);
    const etiquetas = valores.map((_, i) => ((desde + i) % 2 === 0 ? `${desde + i}h` : ""));
    window.Graficas.area(contenedor, valores.length > 1 ? valores : [0, ...valores], {
      etiquetas: valores.length > 1 ? etiquetas : ["", ...etiquetas],
      horaActual: Math.max(1, valores.length - 1),
      alto: 120,
    });
  }

  function pulsar(kpi) {
    if (!kpi) return;
    kpi.classList.remove("pulso");
    void kpi.offsetWidth; // reinicia la animacion
    kpi.classList.add("pulso");
  }

  function sumarAlResumen(orden) {
    const ordenesEl = $("resumen-ordenes");
    const ingresoEl = $("resumen-ingreso");
    if (!ordenesEl || !ingresoEl) return;

    const ordenes = Number(ordenesEl.dataset.valor || 0) + 1;
    const ingreso = Number(ingresoEl.dataset.valor || 0) + Number(orden.total || 0);
    ordenesEl.dataset.valor = ordenes;
    ingresoEl.dataset.valor = ingreso;
    ordenesEl.textContent = ordenes;
    ingresoEl.textContent = pesosMiles(ingreso);
    const ticket = $("resumen-ticket");
    if (ticket) ticket.textContent = `$${Math.round(ingreso / ordenes)}`;
    pulsar(ordenesEl.closest(".kpi"));
    pulsar(ingresoEl.closest(".kpi"));

    if (ordenesPorHora) {
      ordenesPorHora[new Date().getHours()] += 1;
      dibujarGraficaHoy();
    }
  }

  // ---------------- Ventana "Entregas" ----------------

  // Posicion "decorativa" del pin en el mapa: estable para la misma direccion
  // (hash), pero no representa una ubicacion geografica real.
  function posicionPin(texto) {
    let h = 2166136261;
    for (const c of texto) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
    const angulo = ((h >>> 0) % 360) * (Math.PI / 180);
    const radio = 16 + ((h >>> 12) % 26);
    return { left: 50 + Math.cos(angulo) * radio * 1.4, top: 50 + Math.sin(angulo) * radio };
  }

  function renderEntregas() {
    const lista = $("lista-entregas");
    const mapa = $("mapa-entregas");
    if (!lista || !mapa) return;

    const cards = [...document.querySelectorAll('.orden-card[data-tipo="domicilio"]')];
    lista.replaceChildren();
    mapa.querySelectorAll(".mapa-pin").forEach((pin) => pin.remove());

    cards.forEach((card) => {
      const d = card.dataset;
      const item = elemento("li", "entrega");
      item.appendChild(elemento("span", "entrega-numero", d.numero));
      item.appendChild(elemento("span", "entrega-nombre", d.nombre || "Cliente"));
      const estado = elemento("span", `status-pill status-${d.status}`, ESTADO_LABELS[d.status] || d.status);
      item.appendChild(estado);
      item.appendChild(elemento("span", "entrega-direccion", [d.direccion, d.referencias].filter(Boolean).join(" · ")));
      const pie = elemento("span", "entrega-pago");
      if (d.telefono) {
        const tel = elemento("a", undefined, d.telefono);
        tel.href = `tel:${d.telefono}`;
        pie.append(tel, document.createTextNode(d.pago ? ` · ${d.pago}` : ""));
      } else {
        pie.textContent = d.pago;
      }
      item.appendChild(pie);
      lista.appendChild(item);

      const pin = elemento("span", "mapa-pin", d.numero);
      const pos = posicionPin(d.direccion || d.numero);
      pin.style.left = `${Math.min(92, Math.max(8, pos.left))}%`;
      pin.style.top = `${Math.min(90, Math.max(22, pos.top))}%`;
      pin.title = d.direccion;
      mapa.appendChild(pin);
    });

    $("entregas-vacio")?.classList.toggle("oculto", cards.length > 0);
    const dato = document.querySelector("[data-dato-entregas]");
    if (dato) dato.textContent = cards.length ? `${cards.length} en ruta` : "";
  }

  // ---------------- Ventana "Menu rapido" ----------------

  function inicializarMenuRapido() {
    document.querySelectorAll("[data-rapido-toggle]").forEach((boton) => {
      boton.addEventListener("click", async () => {
        const nuevo = boton.dataset.disponible !== "true";
        boton.disabled = true;
        try {
          const respuesta = await fetch(`/api/menu/${boton.dataset.rapidoToggle}/disponibilidad`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ disponible: nuevo }),
          });
          if (!respuesta.ok) throw new Error();
          boton.dataset.disponible = String(nuevo);
          boton.setAttribute("aria-pressed", String(!nuevo));
          boton.classList.toggle("agotado", !nuevo);
        } catch (error) {
          alert("No se pudo actualizar el platillo.");
        } finally {
          boton.disabled = false;
        }
      });
    });
  }

  // ---------------- Alerta de pedidos nuevos ----------------
  // Mientras haya pedidos sin confirmar: aviso arriba, contador en la pestana
  // y un timbre que se repite. El navegador solo deja sonar despues de que
  // alguien toca la pagina, por eso el boton "Activar sonido".

  const REPETIR_TIMBRE_MS = 20000;
  const pedidosSinConfirmar = new Set();
  const tituloOriginal = document.title;
  let audioCtx = null;
  let intervaloTimbre = null;

  function leerPreferenciaSonido() {
    try {
      return localStorage.getItem("sianka-sonido") === "si";
    } catch (error) {
      return false;
    }
  }

  function guardarPreferenciaSonido(activo) {
    try {
      localStorage.setItem("sianka-sonido", activo ? "si" : "no");
    } catch (error) {
      /* sin almacenamiento: la preferencia dura solo esta visita */
    }
  }

  let sonidoActivo = leerPreferenciaSonido();

  function prepararAudio() {
    if (!audioCtx) {
      const Contexto = window.AudioContext || window.webkitAudioContext;
      if (!Contexto) return null;
      audioCtx = new Contexto();
    }
    if (audioCtx.state === "suspended") audioCtx.resume();
    return audioCtx;
  }

  function timbre() {
    if (!sonidoActivo) return;
    const ctx = prepararAudio();
    if (!ctx || ctx.state !== "running") return;
    // Dos tonos cortos, como timbre de mostrador.
    [880, 1175].forEach((frecuencia, i) => {
      const inicio = ctx.currentTime + i * 0.22;
      const osc = ctx.createOscillator();
      const vol = ctx.createGain();
      osc.frequency.value = frecuencia;
      vol.gain.setValueAtTime(0.0001, inicio);
      vol.gain.exponentialRampToValueAtTime(0.35, inicio + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.2);
      osc.connect(vol).connect(ctx.destination);
      osc.start(inicio);
      osc.stop(inicio + 0.21);
    });
  }

  function pintarBotonSonido() {
    const boton = document.querySelector("[data-sonido]");
    if (!boton) return;
    boton.setAttribute("aria-pressed", String(sonidoActivo));
    boton.textContent = sonidoActivo ? "Sonido activado" : "Activar sonido";
  }

  function actualizarAlertaPedidos() {
    const total = pedidosSinConfirmar.size;
    const aviso = document.querySelector("[data-aviso-pedidos]");
    if (aviso) {
      aviso.hidden = total === 0;
      aviso.textContent = total === 1 ? "1 pedido nuevo sin confirmar" : `${total} pedidos nuevos sin confirmar`;
    }
    document.title = total ? `(${total}) Pedido nuevo · ${tituloOriginal}` : tituloOriginal;

    if (total && !intervaloTimbre) {
      intervaloTimbre = setInterval(timbre, REPETIR_TIMBRE_MS);
    } else if (!total && intervaloTimbre) {
      clearInterval(intervaloTimbre);
      intervaloTimbre = null;
    }
  }

  function registrarPedidoNuevo(ordenId) {
    if (!ordenId) return;
    pedidosSinConfirmar.add(String(ordenId));
    actualizarAlertaPedidos();
    timbre();
  }

  function registrarCambioDePedido(ordenId, status) {
    if (status !== "nueva" && pedidosSinConfirmar.delete(String(ordenId))) actualizarAlertaPedidos();
  }

  function inicializarAlertas() {
    document.querySelectorAll('.orden-card[data-status="nueva"]').forEach((card) => {
      pedidosSinConfirmar.add(String(card.dataset.ordenId));
    });
    actualizarAlertaPedidos();
    pintarBotonSonido();

    document.querySelector("[data-sonido]")?.addEventListener("click", () => {
      sonidoActivo = !sonidoActivo;
      guardarPreferenciaSonido(sonidoActivo);
      pintarBotonSonido();
      if (sonidoActivo) timbre();
    });
    // Si el sonido ya estaba activado, el primer toque a la pagina lo desbloquea.
    document.addEventListener("pointerdown", () => sonidoActivo && prepararAudio(), { once: true });
  }

  // ---------------- Reloj ----------------

  function iniciarReloj() {
    const reloj = document.querySelector("[data-reloj]");
    if (!reloj) return;
    const pintar = () => {
      reloj.textContent = new Date().toLocaleString("es-MX", {
        weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      });
    };
    pintar();
    setInterval(pintar, 15000);
  }

  // ---------------- Arranque ----------------

  function inicializarCentroDeMando() {
    document.querySelectorAll(".orden-card").forEach((card) => renderAccionesOrden(card, card.dataset.status));
    actualizarPipelineDesdeDOM();
    renderEntregas();
    inicializarMenuRapido();

    const datos = $("datos-hoy");
    if (datos) {
      try {
        ordenesPorHora = JSON.parse(datos.textContent).ordenes_por_hora;
      } catch (error) {
        ordenesPorHora = null;
      }
      dibujarGraficaHoy();
      window.Graficas?.alRedimensionar($("grafica-hoy"), dibujarGraficaHoy);
    }
  }

  window.renderAccionesOrden = renderAccionesOrden;
  window.actualizarPipelineDesdeDOM = actualizarPipelineDesdeDOM;
  window.inicializarCentroDeMando = inicializarCentroDeMando;

  document.addEventListener("DOMContentLoaded", () => {
    iniciarReloj();
    inicializarAlertas();
    actualizarTiemposTranscurridos();
    setInterval(actualizarTiemposTranscurridos, 30000);
    conectarWebSocket();
  });
})();
