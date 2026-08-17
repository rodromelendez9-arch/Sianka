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

  function crearTarjetaOrden(orden) {
    const card = document.createElement("article");
    card.className = "orden-card";
    card.dataset.ordenId = orden.orden_id;
    card.dataset.status = orden.status || "nueva";
    card.dataset.created = orden.timestamp || new Date().toISOString();

    const header = document.createElement("div");
    header.className = "orden-card-header";

    const numero = document.createElement("span");
    numero.className = "orden-numero";
    numero.textContent = `Orden #${(orden.orden_id || "").slice(0, 8)}`;

    const tiempo = document.createElement("span");
    tiempo.className = "orden-tiempo-transcurrido";
    tiempo.dataset.created = card.dataset.created;
    tiempo.textContent = "hace un momento";

    header.appendChild(numero);
    header.appendChild(tiempo);

    const pill = document.createElement("span");
    pill.className = `status-pill status-${card.dataset.status}`;
    pill.textContent = ESTADO_LABELS[card.dataset.status] || card.dataset.status;

    const items = document.createElement("div");
    items.className = "orden-items";
    (orden.items || []).forEach((item) => {
      const linea = document.createElement("div");
      linea.className = "orden-item";
      const nombre = document.createElement("span");
      nombre.innerHTML = `<span class="cantidad">${item.cantidad}x</span>${item.platillo}`;
      const precio = document.createElement("span");
      precio.textContent = `$${Number(item.subtotal).toFixed(2)}`;
      linea.appendChild(nombre);
      linea.appendChild(precio);
      items.appendChild(linea);
    });

    const total = document.createElement("div");
    total.className = "orden-total";
    const totalLabel = document.createElement("span");
    totalLabel.textContent = "Total";
    const totalValor = document.createElement("span");
    totalValor.textContent = `$${Number(orden.total || 0).toFixed(2)}`;
    total.appendChild(totalLabel);
    total.appendChild(totalValor);

    const recoleccion = document.createElement("div");
    recoleccion.className = "orden-recoleccion";
    recoleccion.textContent = `Recoleccion: ${orden.recoleccion || "20 minutos"}`;

    const acciones = document.createElement("div");
    acciones.className = "orden-acciones";
    acciones.setAttribute("data-acciones", "");

    card.appendChild(header);
    card.appendChild(pill);
    card.appendChild(items);
    card.appendChild(total);
    card.appendChild(recoleccion);
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
    const definiciones = ACCIONES_POR_ESTADO[status] || [];

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
