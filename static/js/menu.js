const formNuevoPlatillo = document.getElementById("form-nuevo-platillo");

formNuevoPlatillo.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const body = {
    platillo: document.getElementById("nuevo-platillo").value,
    precio: parseFloat(document.getElementById("nuevo-precio").value),
    ingredientes: document.getElementById("nuevo-ingredientes").value || null,
  };

  const respuesta = await fetch("/api/menu", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (respuesta.ok) {
    window.location.reload();
  } else {
    alert("No se pudo agregar el platillo.");
  }
});

document.querySelectorAll("[data-disponibilidad-toggle]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const menuId = boton.dataset.disponibilidadToggle;
    const disponibleActual = boton.dataset.disponible === "true";
    const nuevoDisponible = !disponibleActual;

    const respuesta = await fetch(`/api/menu/${menuId}/disponibilidad`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disponible: nuevoDisponible }),
    });

    if (!respuesta.ok) {
      alert("No se pudo actualizar la disponibilidad.");
      return;
    }

    boton.dataset.disponible = String(nuevoDisponible);
    boton.setAttribute("aria-pressed", String(nuevoDisponible));
    boton.classList.toggle("agotado", !nuevoDisponible);
    boton.querySelector(".disponibilidad-texto").textContent = nuevoDisponible ? "Disponible" : "Agotado";
    boton.closest(".menu-item-card").classList.toggle("agotado", !nuevoDisponible);
  });
});

document.querySelectorAll("[data-eliminar-platillo]").forEach((boton) => {
  boton.addEventListener("click", async () => {
    const menuId = boton.dataset.eliminarPlatillo;
    if (!confirm("¿Eliminar este platillo del menu?")) return;

    const respuesta = await fetch(`/api/menu/${menuId}`, { method: "DELETE" });
    if (respuesta.ok) {
      boton.closest(".menu-item-card").remove();
    } else {
      alert("No se pudo eliminar el platillo.");
    }
  });
});
