/* Pagina de venta de Sianka: movimiento sin librerias externas (la CSP solo
 * permite scripts propios). Todo se desactiva o simplifica con
 * prefers-reduced-motion, y el paralaje de raton solo corre con puntero fino.
 */
(function () {
  const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const punteroFino = window.matchMedia("(pointer: fine)").matches;
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];
  const formato = (n) => n.toLocaleString("es-MX", { maximumFractionDigits: 0 });

  // ---------------- Carga: lineas enmascaradas del titulo ----------------
  requestAnimationFrame(() => document.body.classList.add("cargado"));

  // ---------------- Barra: solida al bajar y seccion activa ----------------
  const barra = $("[data-barra]");
  const enlacesNav = $$(".barra-nav a");
  const alBajar = () => barra?.classList.toggle("solida", window.scrollY > 24);
  window.addEventListener("scroll", alBajar, { passive: true });
  alBajar();

  if ("IntersectionObserver" in window) {
    const porSeccion = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((e) => {
          if (!e.isIntersecting) return;
          enlacesNav.forEach((a) => a.classList.toggle("activo", a.getAttribute("href") === `#${e.target.id}`));
        });
      },
      { rootMargin: "-45% 0px -50% 0px" }
    );
    $$("section[id]").forEach((s) => porSeccion.observe(s));
  }

  // ---------------- Aparicion escalonada al entrar en pantalla ----------------
  const revelables = $$(".revelar");
  revelables.forEach((el) => {
    const hermanos = $$(":scope > .revelar", el.parentElement);
    el.style.setProperty("--retraso", `${Math.min(hermanos.indexOf(el), 6) * 0.08}s`);
  });
  if (reducido || !("IntersectionObserver" in window)) {
    revelables.forEach((el) => el.classList.add("visible"));
  } else {
    const observador = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("visible");
            observador.unobserve(e.target);
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -6% 0px" }
    );
    revelables.forEach((el) => observador.observe(el));
  }

  // ---------------- Palabra que rota en el titulo ----------------
  const rotativa = $("[data-rotar]");
  if (rotativa && !reducido) {
    const palabras = JSON.parse(rotativa.dataset.rotar);
    let i = 0;
    setInterval(() => {
      rotativa.classList.add("saliendo");
      setTimeout(() => {
        i = (i + 1) % palabras.length;
        rotativa.textContent = palabras[i];
        rotativa.classList.remove("saliendo");
      }, 350);
    }, 2800);
  }

  // ---------------- Palabras que se encienden con el scroll ----------------
  const iluminables = $$("[data-iluminar]");
  iluminables.forEach((el) => {
    const palabras = el.textContent.trim().split(/\s+/);
    el.replaceChildren(
      ...palabras.flatMap((p, i) => {
        const s = document.createElement("span");
        s.className = "palabra";
        s.textContent = p;
        return i < palabras.length - 1 ? [s, document.createTextNode(" ")] : [s];
      })
    );
  });

  // ---------------- Paralaje por capas (data-depth 0-5) ----------------
  // Factor de movimiento por profundidad: el fondo casi no se mueve, el
  // primer plano se mueve mas que la pagina (sensacion de espacio).
  const FACTOR = { 0: 0.1, 1: 0.25, 2: 0.5, 3: 0.8, 4: 1, 5: 1.2 };
  const hero = $(".hero");
  const capasHero = hero ? $$("[data-depth]", hero) : [];
  const capasOtras = $$("section:not(.hero) [data-depth]");
  let raton = { x: 0, y: 0 };
  if (punteroFino && !reducido && hero) {
    hero.addEventListener("pointermove", (e) => {
      const r = hero.getBoundingClientRect();
      raton = { x: (e.clientX - r.left) / r.width - 0.5, y: (e.clientY - r.top) / r.height - 0.5 };
      pedirCuadro();
    });
    hero.addEventListener("pointerleave", () => {
      raton = { x: 0, y: 0 };
      pedirCuadro();
    });
  }

  // ---------------- Vista del panel: se endereza con el scroll ----------------
  const maqueta = $("[data-perspectiva]");

  function progresoEnPantalla(el) {
    const r = el.getBoundingClientRect();
    const alto = window.innerHeight;
    return Math.min(1, Math.max(0, (alto - r.top) / (alto + r.height)));
  }

  let cuadroPendiente = false;
  function pedirCuadro() {
    if (!cuadroPendiente) {
      cuadroPendiente = true;
      requestAnimationFrame(dibujar);
    }
  }

  function dibujar() {
    cuadroPendiente = false;
    if (reducido) return;
    const y = window.scrollY;

    if (hero && y < hero.offsetHeight * 1.2) {
      capasHero.forEach((capa) => {
        const f = FACTOR[capa.dataset.depth] ?? 1;
        if (f === 1) return; // el texto se mueve con la pagina
        const ty = y * (1 - f) * 0.35 + raton.y * f * 22;
        const tx = raton.x * f * 30;
        capa.style.transform = `translate3d(${tx.toFixed(1)}px, ${ty.toFixed(1)}px, 0)`;
      });
    }

    capasOtras.forEach((capa) => {
      const seccion = capa.closest("section");
      const p = progresoEnPantalla(seccion) - 0.5;
      const f = FACTOR[capa.dataset.depth] ?? 1;
      capa.style.transform = `translate3d(0, ${(p * (1 - f) * 160).toFixed(1)}px, 0)`;
    });

    iluminables.forEach((el) => {
      const r = el.getBoundingClientRect();
      const avance = Math.min(1, Math.max(0, (window.innerHeight * 0.85 - r.top) / (r.height + window.innerHeight * 0.35)));
      const palabras = $$(".palabra", el);
      const encendidas = Math.round(avance * palabras.length);
      palabras.forEach((p, i) => p.classList.toggle("encendida", i < encendidas));
    });

    if (maqueta) {
      const p = Math.min(1, progresoEnPantalla(maqueta.parentElement) * 1.7);
      maqueta.style.transform = `rotateX(${(24 * (1 - p)).toFixed(2)}deg) scale(${(0.9 + 0.1 * p).toFixed(3)})`;
    }
  }

  if (reducido) {
    $$(".palabra").forEach((p) => p.classList.add("encendida"));
  } else {
    window.addEventListener("scroll", pedirCuadro, { passive: true });
    window.addEventListener("resize", pedirCuadro);
    pedirCuadro();
  }

  // ---------------- Tarjetas que se inclinan hacia el raton ----------------
  if (punteroFino && !reducido) {
    $$("[data-inclinar]").forEach((tarjeta) => {
      tarjeta.addEventListener("pointermove", (e) => {
        if (!tarjeta.classList.contains("visible")) return;
        const r = tarjeta.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        tarjeta.style.transform = `perspective(700px) rotateX(${(-y * 7).toFixed(2)}deg) rotateY(${(x * 9).toFixed(2)}deg) translateY(-4px)`;
      });
      tarjeta.addEventListener("pointerleave", () => (tarjeta.style.transform = ""));
    });
  }

  // ---------------- Como funciona: el telefono sigue al paso activo ----------------
  const pasos = $$("[data-paso]");
  const visual = $("[data-paso-visual]");
  if (pasos.length && visual) {
    const activar = (n) => {
      pasos.forEach((p) => p.classList.toggle("activo", p.dataset.paso === n));
      visual.dataset.pasoVisual = n;
    };
    activar("1");
    if ("IntersectionObserver" in window) {
      const obs = new IntersectionObserver(
        (entradas) => entradas.forEach((e) => e.isIntersecting && activar(e.target.dataset.paso)),
        { rootMargin: "-45% 0px -45% 0px" }
      );
      pasos.forEach((p) => obs.observe(p));
    }
  }

  // ---------------- Contadores de la maqueta ----------------
  function contar(el) {
    const meta = Number(el.dataset.contar);
    const prefijo = el.dataset.prefijo || "";
    const sufijo = el.dataset.sufijo || "";
    const inicio = performance.now();
    const duracion = 1400;
    (function paso(ahora) {
      const t = Math.min(1, (ahora - inicio) / duracion);
      const suave = 1 - Math.pow(1 - t, 3);
      el.textContent = `${prefijo}${formato(Math.round(meta * suave))}${sufijo}`;
      if (t < 1) requestAnimationFrame(paso);
    })(inicio);
    setTimeout(() => (el.textContent = `${prefijo}${formato(meta)}${sufijo}`), duracion + 200);
  }
  const contadores = $$("[data-contar]");
  if (!reducido && "IntersectionObserver" in window) {
    const obs = new IntersectionObserver(
      (entradas) => {
        entradas.forEach((e) => {
          if (e.isIntersecting) {
            contar(e.target);
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.6 }
    );
    contadores.forEach((c) => obs.observe(c));
  }

  // ---------------- Calculadora ----------------
  const calculadora = $("[data-calculadora]");
  if (calculadora) {
    const resultado = $("[data-resultado]", calculadora);
    let mostrado = 0;
    let animacion = null;
    let calculadoraMeta = null;
    const actualizar = () => {
      const v = Object.fromEntries([...new FormData(calculadora)].map(([k, x]) => [k, Number(x)]));
      $('[data-salida="llamadas"]', calculadora).textContent = v.llamadas;
      $('[data-salida="ticket"]', calculadora).textContent = `$${formato(v.ticket)}`;
      $('[data-salida="dias"]', calculadora).textContent = v.dias;
      const meta = v.llamadas * v.ticket * v.dias;
      cancelAnimationFrame(animacion);
      if (reducido) {
        mostrado = meta;
        resultado.textContent = `$${formato(meta)}`;
        return;
      }
      const desde = mostrado;
      const inicio = performance.now();
      (function paso(ahora) {
        const t = Math.min(1, (ahora - inicio) / 450);
        mostrado = desde + (meta - desde) * (1 - Math.pow(1 - t, 3));
        resultado.textContent = `$${formato(Math.round(mostrado))}`;
        if (t < 1) animacion = requestAnimationFrame(paso);
      })(inicio);
      // Si el navegador pausa requestAnimationFrame (pestana en segundo
      // plano), el valor final se escribe igual: la animacion es decorativa.
      setTimeout(() => {
        if (Math.round(mostrado) !== meta && calculadoraMeta === meta) {
          cancelAnimationFrame(animacion);
          mostrado = meta;
          resultado.textContent = `$${formato(meta)}`;
        }
      }, 600);
      calculadoraMeta = meta;
    };
    calculadora.addEventListener("input", actualizar);
    calculadora.addEventListener("submit", (e) => e.preventDefault());
    actualizar();
  }

  // ---------------- Hero: una llamada que se convierte en pedido ----------------
  const chat = $("[data-hero-chat]");
  if (!chat) return;
  const estado = $("[data-hero-estado]");
  const tiempo = $("[data-hero-tiempo]");
  const barras = $$(".telefono-onda i");
  const comanda = $("[data-hero-comanda]");
  const cliente = $("[data-hero-cliente]");
  const items = $("[data-hero-items]");
  const total = $("[data-hero-total]");

  const GUION = [
    { quien: "agente", texto: "¡Hola, gracias por llamar a Taquería La Esquina! ¿Qué te preparamos hoy?" },
    { quien: "cliente", texto: "Quiero tres de cochinita y una horchata" },
    { quien: "agente", texto: "¡Va! ¿Algo más?", agregar: [["taco", "3x Cochinita", 75], ["agua-horchata", "1x Horchata", 20]] },
    { quien: "cliente", texto: "Y dos de bistec. A nombre de Luis, paso por ellos" },
    { quien: "agente", texto: "Listo Luis: son $151. Tu orden es la 42, en 20 minutos.", agregar: [["taco", "2x Bistec", 56]], nombre: "Luis · Recoger", enviar: true },
  ];

  let reloj = null;
  let segundos = 0;
  let enPantalla = true;
  const esperar = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const esperarVisible = async () => {
    while (!enPantalla || document.hidden) await esperar(400);
  };

  function hablar(activo) {
    barras.forEach((b) => {
      b.style.transform = `scaleY(${activo ? (0.25 + Math.random() * 0.75).toFixed(2) : 0.12})`;
    });
  }

  function burbuja(quien, texto) {
    const p = document.createElement("p");
    p.className = `burbuja ${quien}`;
    p.textContent = texto;
    chat.appendChild(p);
    while (chat.children.length > 4) chat.firstElementChild.remove();
    return p;
  }

  function agregarItem([ilustracion, etiqueta, precio]) {
    const li = document.createElement("li");
    const img = document.createElement("img");
    img.src = `/static/img/platillos/${ilustracion}.svg`;
    img.alt = "";
    const nombre = document.createElement("span");
    nombre.textContent = etiqueta;
    const importe = document.createElement("span");
    importe.textContent = `$${precio}`;
    li.append(img, nombre, importe);
    items.appendChild(li);
    const suma = $$("li", items).reduce((s, el) => s + Number(el.lastChild.textContent.slice(1)), 0);
    total.textContent = `$${suma}`;
  }

  function estadoFinal() {
    GUION.forEach((l) => burbuja(l.quien, l.texto));
    GUION.forEach((l) => (l.agregar || []).forEach(agregarItem));
    cliente.textContent = "Luis · Recoger";
    estado.textContent = "Pedido en cocina";
    comanda.classList.add("enviada");
  }

  if (reducido) {
    estadoFinal();
    return;
  }

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => (enPantalla = e.isIntersecting)).observe(chat);
  }

  async function reproducir() {
    for (;;) {
      chat.replaceChildren();
      items.replaceChildren();
      total.textContent = "$0";
      cliente.textContent = "—";
      comanda.classList.remove("enviada");
      estado.textContent = "Llamada entrante";
      segundos = 0;
      tiempo.textContent = "00:00";
      await esperar(1200);
      estado.textContent = "En llamada";
      clearInterval(reloj);
      reloj = setInterval(() => {
        segundos += 1;
        tiempo.textContent = `00:${String(segundos).padStart(2, "0")}`;
      }, 1000);

      for (const linea of GUION) {
        await esperarVisible();
        const p = burbuja(linea.quien, "");
        p.classList.add("escribiendo");
        const onda = setInterval(() => hablar(true), 140);
        // Se "escribe" palabra por palabra, como si se estuviera hablando
        const palabras = linea.texto.split(" ");
        for (let i = 1; i <= palabras.length; i++) {
          p.textContent = palabras.slice(0, i).join(" ");
          await esperar(linea.quien === "agente" ? 95 : 130);
        }
        p.classList.remove("escribiendo");
        clearInterval(onda);
        hablar(false);
        (linea.agregar || []).forEach(agregarItem);
        if (linea.nombre) cliente.textContent = linea.nombre;
        if (linea.enviar) {
          await esperar(500);
          comanda.classList.add("enviada");
          estado.textContent = "Pedido en cocina";
        }
        await esperar(850);
      }
      clearInterval(reloj);
      await esperar(3800);
    }
  }

  reproducir();
})();
