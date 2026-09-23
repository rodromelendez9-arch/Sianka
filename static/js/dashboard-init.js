document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".orden-card").forEach((card) => {
    window.renderAccionesOrden(card, card.dataset.status);
  });
  window.actualizarPipelineDesdeDOM();
});
