/* Graficas SVG sin librerias (la CSP del sitio no permite scripts externos).
 * Se exponen en window.Graficas:
 *   area(contenedor, valores, {etiquetas, horaActual})  -> linea con area
 *   barras(contenedor, valores, etiquetas)               -> barras verticales
 */
(function () {
  const NS = "http://www.w3.org/2000/svg";

  function nodo(tipo, atributos = {}, texto) {
    const el = document.createElementNS(NS, tipo);
    Object.entries(atributos).forEach(([k, v]) => el.setAttribute(k, v));
    if (texto !== undefined) el.textContent = texto;
    return el;
  }

  // El SVG usa el ancho REAL del contenedor (no un viewBox fijo escalado):
  // asi la altura no crece con el ancho y los textos no se deforman.
  function lienzo(contenedor, alto) {
    contenedor.replaceChildren();
    const ancho = Math.max(200, contenedor.clientWidth);
    const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, width: ancho, height: alto });
    contenedor.appendChild(svg);
    return { svg, ancho };
  }

  function area(contenedor, valores, opciones = {}) {
    if (!contenedor) return;
    const H = opciones.alto || 130, M = { t: 10, r: 8, b: 22, l: 8 };
    const { svg, ancho: W } = lienzo(contenedor, H);
    const max = Math.max(1, ...valores);
    const paso = (W - M.l - M.r) / Math.max(1, valores.length - 1);
    const x = (i) => M.l + i * paso;
    const y = (v) => M.t + (H - M.t - M.b) * (1 - v / max);

    const defs = nodo("defs");
    const degradado = nodo("linearGradient", { id: "degradado-area", x1: "0", x2: "0", y1: "0", y2: "1" });
    degradado.append(
      nodo("stop", { offset: "0%", "stop-color": "#38bdf8", "stop-opacity": "0.45" }),
      nodo("stop", { offset: "100%", "stop-color": "#38bdf8", "stop-opacity": "0" })
    );
    defs.appendChild(degradado);
    svg.appendChild(defs);

    [0.5, 1].forEach((f) => {
      svg.appendChild(nodo("line", { class: "guia", x1: M.l, x2: W - M.r, y1: y(max * f), y2: y(max * f) }));
    });

    // Curva suavizada (Catmull-Rom a Bezier) para que no se vea "de escalera"
    const puntos = valores.map((v, i) => [x(i), y(v)]);
    let d = `M${puntos[0][0]},${puntos[0][1]}`;
    for (let i = 0; i < puntos.length - 1; i++) {
      const p0 = puntos[i - 1] || puntos[i], p1 = puntos[i], p2 = puntos[i + 1], p3 = puntos[i + 2] || p2;
      const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
      const c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
      d += ` C${c1},${c2},${p2}`;
    }
    svg.appendChild(nodo("path", { class: "area", d: `${d} L${x(valores.length - 1)},${H - M.b} L${x(0)},${H - M.b} Z` }));
    svg.appendChild(nodo("path", { class: "linea", d }));

    const etiquetas = opciones.etiquetas || [];
    etiquetas.forEach((texto, i) => {
      if (texto) svg.appendChild(nodo("text", { class: "eje", x: x(i), y: H - 6, "text-anchor": "middle" }, texto));
    });

    if (opciones.horaActual !== undefined && valores[opciones.horaActual] !== undefined) {
      const i = opciones.horaActual;
      svg.appendChild(nodo("circle", { class: "punto-actual", cx: x(i), cy: y(valores[i]), r: 4 }));
    }
  }

  function barras(contenedor, valores, etiquetas = [], alto = 190) {
    if (!contenedor) return;
    const H = alto, M = { t: 16, r: 4, b: 22, l: 4 };
    const { svg, ancho: W } = lienzo(contenedor, H);
    const max = Math.max(1, ...valores);
    const ancho = (W - M.l - M.r) / valores.length;
    const indiceMax = valores.indexOf(Math.max(...valores));

    valores.forEach((v, i) => {
      const alto = (H - M.t - M.b) * (v / max);
      const bx = M.l + i * ancho + ancho * 0.18;
      const by = H - M.b - alto;
      const barra = nodo("rect", {
        class: `barra${i === indiceMax && v > 0 ? " maxima" : ""}`,
        x: bx, y: by, width: ancho * 0.64, height: Math.max(alto, v > 0 ? 2 : 0), rx: 3,
      });
      barra.appendChild(nodo("title", {}, `${etiquetas[i] || i}: ${v}`));
      svg.appendChild(barra);
      if (v > 0 && valores.length <= 12) {
        svg.appendChild(nodo("text", { class: "valor-barra", x: bx + ancho * 0.32, y: by - 4, "text-anchor": "middle" }, v));
      }
      if (etiquetas[i]) {
        svg.appendChild(nodo("text", { class: "eje", x: bx + ancho * 0.32, y: H - 6, "text-anchor": "middle" }, etiquetas[i]));
      }
    });
  }

  // Redibuja cuando cambia el ancho del contenedor (ventana redimensionada)
  function alRedimensionar(contenedor, dibujar) {
    if (!contenedor) return;
    let ancho = contenedor.clientWidth;
    new ResizeObserver(() => {
      if (Math.abs(contenedor.clientWidth - ancho) > 4) {
        ancho = contenedor.clientWidth;
        dibujar();
      }
    }).observe(contenedor);
  }

  window.Graficas = { area, barras, alRedimensionar };
})();
