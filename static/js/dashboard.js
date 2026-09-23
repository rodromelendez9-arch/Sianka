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
    confirmada: [
      { label: "Iniciar preparacion", siguiente: "preparando", clase: "btn-primary" },
    ],
    preparando: [
      { label: "Lista para recoger", siguiente: "lista", clase: "btn-primary" },
    ],
    lista: [
      { label: "Marcar entregada", siguiente: "entregada", clase: "btn-primary" },
    ],
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

  function conectarWebSocket() {
    const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocolo}//${location.host}/ws/dashboard`;
    const socket = new WebSocket(url);

    socket.addEventListener("message", (evento) => {
      let data;
      try {
        data = JSON.parse(evento.data);
      } catch (error) {
        return;
      }
      manejarEvento(data);
    });

    socket.addEventListener("close", () => {
      setTimeout(conectarWebSocket, 3000);
    });

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
        break;
      case "orden_actualizada":
        actualizarStatusOrden(data);
        break;
      case "llamada_terminada":
        ocultarLlamadaActiva();
        break;
      default:
        break;
    }
  }

  function mostrarLlamadaActiva(data) {
    const contenedor = document.getElementById("llamada-activa");
    if (!contenedor) return;

    contenedor.classList.remove("oculto");

    const telefono = document.getElementById("llamada-telefono");
    if (telefono) telefono.textContent = data.telefono_cliente || "Desconocido";

    const transcripcion = document.getElementById("llamada-transcripcion");
    if (transcripcion) transcripcion.innerHTML = "";

    const estado = document.getElementById("llamada-estado");
    if (estado) estado.textContent = "Identificando intencion";

    llamadaInicioTimestamp = Date.now();
    iniciarTimer();
  }

  function ocultarLlamadaActiva() {
    const contenedor = document.getElementById("llamada-activa");
    if (contenedor) contenedor.classList.add("oculto");
    detenerTimer();
  }

  function iniciarTimer() {
    detenerTimer();
    const timerEl = document.getElementById("llamada-timer");
    if (!timerEl) return;

    timerInterval = setInterval(() => {
      const segundos = Math.floor((Date.now() - llamadaInicioTimestamp) / 1000);
      const min = Math.floor(segundos / 60).toString().padStart(2, "0");
      const seg = (segundos % 60).toString().padStart(2, "0");
      timerEl.textContent = `${min}:${seg}`;
    }, 1000);
  }

  function detenerTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  function actualizarTranscripcion(data) {
    const contenedor = document.getElementById("llamada-transcripcion");
    if (!contenedor) return;

    const linea = document.createElement("div");
    linea.className = `linea ${data.hablante === "agente" ? "agente" : "cliente"}`;

    const hablanteEl = document.createElement("span");
    hablanteEl.className = "hablante";
    hablanteEl.textContent = data.hablante === "agente" ? "Agente:" : "Cliente:";

    linea.appendChild(hablanteEl);
    linea.appendChild(document.createTextNode(data.texto || ""));

    contenedor.appendChild(linea);
    contenedor.scrollTop = contenedor.scrollHeight;

    const estado = document.getElementById("llamada-estado");
    if (estado && data.hablante !== "agente") {
      estado.textContent = "Tomando orden";
    }
  }

  function elemento(tag, clase, texto) {
    const el = document.createElement(tag);
    if (clase) el.className = clase;
    if (texto !== undefined) el.textContent = texto;
    return el;
  }

  function pesos(valor) {
    return `$${Number(valor || 0).toFixed(2)}`;
  }

  function lineaItem(etiqueta, monto, cantidad, claseExtra) {
    const linea = elemento("div", `orden-item${claseExtra ? ` ${claseExtra}` : ""}`);
    const nombre = elemento("span");
    if (cantidad !== undefined) nombre.appendChild(elemento("span", "cantidad", `${cantidad}x`));
    nombre.appendChild(document.createTextNode(etiqueta || ""));
    linea.appendChild(nombre);
    linea.appendChild(elemento("span", undefined, pesos(monto)));
    return linea;
  }

  // Numero diario 001-999 para el mostrador; el id solo como respaldo.
  function etiquetaNumero(orden) {
    if (orden.numero_dia) return `Orden ${String(orden.numero_dia).padStart(3, "0")}`;
    return `Orden #${(orden.orden_id || "").slice(0, 8)}`;
  }

  function crearBloqueEntrega(orden) {
    const bloque = elemento("div", "orden-entrega");
    bloque.appendChild(elemento("div", "orden-entrega-direccion", orden.direccion_entrega || "Direccion no disponible"));
    if (orden.referencias_entrega) {
      bloque.appendChild(elemento("div", "orden-entrega-detalle", orden.referencias_entrega));
    }
    if (orden.telefono_contacto) {
      const telefono = elemento("a", "orden-entrega-telefono", orden.telefono_contacto);
      telefono.href = `tel:${orden.telefono_contacto}`;
      bloque.appendChild(telefono);
    }
    let pago = "";
    if (orden.metodo_pago === "efectivo") {
      pago = "Paga en efectivo";
      if (orden.paga_con) {
        pago += ` con ${pesos(orden.paga_con)} · cambio ${pesos(orden.paga_con - orden.total)}`;
      }
    } else if (orden.metodo_pago === "tarjeta") {
      pago = "Paga con tarjeta (llevar terminal)";
    }
    if (pago) bloque.appendChild(elemento("div", "orden-entrega-detalle", pago));
    return bloque;
  }

  function crearTarjetaOrden(orden) {
    const aDomicilio = orden.tipo_entrega === "domicilio";

    const card = elemento("article", "orden-card");
    card.dataset.ordenId = orden.orden_id;
    card.dataset.status = orden.status || "nueva";
    card.dataset.tipo = aDomicilio ? "domicilio" : "recoger";
    card.dataset.created = orden.timestamp || new Date().toISOString();

    const header = elemento("div", "orden-card-header");
    header.appendChild(elemento("span", "orden-numero", etiquetaNumero(orden)));
    const tiempo = elemento("span", "orden-tiempo-transcurrido", "hace un momento");
    tiempo.dataset.created = card.dataset.created;
    header.appendChild(tiempo);
    card.appendChild(header);

    if (orden.nombre_cliente) card.appendChild(elemento("div", "orden-cliente", orden.nombre_cliente));

    const pills = elemento("div", "orden-pills");
    pills.appendChild(
      elemento("span", `status-pill status-${card.dataset.status}`, ESTADO_LABELS[card.dataset.status] || card.dataset.status)
    );
    pills.appendChild(
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
    total.appendChild(elemento("span", undefined, "Total"));
    total.appendChild(elemento("span", undefined, pesos(orden.total)));
    card.appendChild(total);

    if (aDomicilio) card.appendChild(crearBloqueEntrega(orden));

    card.appendChild(
      elemento("div", "orden-recoleccion", `${aDomicilio ? "Entrega" : "Recoleccion"}: ${orden.recoleccion || ""}`)
    );

    const acciones = elemento("div", "orden-acciones");
    acciones.setAttribute("data-acciones", "");
    card.appendChild(acciones);

    renderAccionesOrden(card, card.dataset.status);

    return card;
  }

  function agregarOrdenNueva(data) {
    const grid = document.getElementById("grid-ordenes");
    if (!grid) return;

    const vacio = grid.querySelector(".estado-vacio");
    if (vacio) vacio.remove();

    const card = crearTarjetaOrden(data);
    grid.prepend(card);
    actualizarPipelineDesdeDOM();
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

    if (data.status === "entregada") {
      card.remove();
    } else {
      renderAccionesOrden(card, data.status);
    }

    actualizarPipelineDesdeDOM();
  }

  function renderAccionesOrden(card, status) {
    const acciones = card.querySelector("[data-acciones]");
    if (!acciones) return;

    acciones.innerHTML = "";
    const definiciones = (ACCIONES_POR_ESTADO[status] || []).map((accion) =>
      card.dataset.tipo === "domicilio" && ETIQUETAS_DOMICILIO[`${status}>${accion.siguiente}`]
        ? { ...accion, label: ETIQUETAS_DOMICILIO[`${status}>${accion.siguiente}`] }
        : accion
    );

    definiciones.forEach((accion) => {
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = `btn ${accion.clase}`;
      boton.textContent = accion.label;
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
    const pipeline = document.getElementById("pipeline");
    if (!pipeline) return;

    const conteos = { nueva: 0, confirmada: 0, preparando: 0, lista: 0, entregada: 0 };

    document.querySelectorAll(".orden-card").forEach((card) => {
      const status = card.dataset.status;
      if (conteos[status] !== undefined) conteos[status] += 1;
    });

    ESTADOS.forEach((status) => {
      const numeroEl = document.getElementById(`pipeline-count-${status}`);
      if (numeroEl) numeroEl.textContent = conteos[status];

      const etapaEl = document.getElementById(`pipeline-${status}`);
      if (etapaEl) {
        etapaEl.classList.toggle("activa", conteos[status] > 0);
      }
    });
  }

  function actualizarTiemposTranscurridos() {
    document.querySelectorAll(".orden-tiempo-transcurrido[data-created]").forEach((el) => {
      const creado = new Date(el.dataset.created).getTime();
      if (Number.isNaN(creado)) return;

      const minutos = Math.floor((Date.now() - creado) / 60000);
      el.textContent = minutos <= 0 ? "hace un momento" : `hace ${minutos} min`;
    });
  }

  function inicializarResumenColapsable() {
    const resumen = document.getElementById("resumen");
    const header = document.getElementById("resumen-header");
    if (!resumen || !header) return;

    header.addEventListener("click", () => {
      resumen.classList.toggle("abierto");
    });
  }

  window.renderAccionesOrden = renderAccionesOrden;
  window.actualizarPipelineDesdeDOM = actualizarPipelineDesdeDOM;

  document.addEventListener("DOMContentLoaded", () => {
    inicializarResumenColapsable();
    actualizarTiemposTranscurridos();
    setInterval(actualizarTiemposTranscurridos, 30000);
    conectarWebSocket();
  });
})();
