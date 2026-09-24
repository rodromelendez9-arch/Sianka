/* Graficas de /reportes. Los datos vienen del servidor en #datos-reportes. */
document.addEventListener("DOMContentLoaded", () => {
  const nodo = document.getElementById("datos-reportes");
  if (!nodo || !window.Graficas) return;

  let datos;
  try {
    datos = JSON.parse(nodo.textContent);
  } catch (error) {
    return;
  }

  const horas = document.getElementById("grafica-horas");
  const dibujarHoras = () =>
    window.Graficas.barras(horas, datos.llamadas_por_hora, datos.llamadas_por_hora.map((_, h) => (h % 3 === 0 ? `${h}h` : "")));

  const dias = document.getElementById("grafica-dias");
  const dibujarDias = () =>
    window.Graficas.barras(dias, datos.ordenes_por_dia.map((d) => d.ordenes), datos.ordenes_por_dia.map((d) => d.dia.slice(0, 3)));

  dibujarHoras();
  dibujarDias();
  window.Graficas.alRedimensionar(horas, dibujarHoras);
  window.Graficas.alRedimensionar(dias, dibujarDias);

  // Ancho de las barras del ranking (la CSP no permite style="" en el HTML)
  document.querySelectorAll(".ranking-barra span[data-porcentaje]").forEach((barra) => {
    barra.style.setProperty("--porcentaje", `${barra.dataset.porcentaje}%`);
  });
});
