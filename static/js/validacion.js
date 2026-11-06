import {
  cerrarSesion,
  crearCelda,
  mostrarToast,
  pedirJson,
  verificarServidor,
} from "./common.js";

const estadoServidor = document.getElementById("estado-servidor");
const btnCargar = document.getElementById("btn-cargar-orden");
const archivoOrden = document.getElementById("archivo-orden");
const nombreOrden = document.getElementById("nombre-orden");
const detalleOrden = document.getElementById("detalle-orden");
const progreso = document.getElementById("progreso");
const feedbackEl = document.getElementById("feedback");
const scanInput = document.getElementById("scan-input");
const btnEscanear = document.getElementById("btn-escanear");
const btnReiniciar = document.getElementById("btn-reiniciar");
const btnExportar = document.getElementById("btn-exportar");
const tablaResultados = document.getElementById("tabla-resultados");
const tablaVacia = document.getElementById("tabla-vacia");
const resumenTabla = document.getElementById("resumen-tabla");
const btnCargarNota = document.getElementById("btn-cargar-nota");
const archivoNota = document.getElementById("archivo-nota");
const estadoNota = document.getElementById("estado-nota");
const revisionNota = document.getElementById("revision-nota");
const advertenciasNota = document.getElementById("advertencias-nota");
const tablaNota = document.getElementById("tabla-nota");
const btnConfirmarNota = document.getElementById("btn-confirmar-nota");
const btnCancelarNota = document.getElementById("btn-cancelar-nota");

let estado = null;
let ocupado = false;
let ocupadoNota = false;
const MAX_BYTES_NOTA = 20 * 1024 * 1024;

function feedback(mensaje, variante = "neutral") {
  feedbackEl.textContent = mensaje;
  feedbackEl.className = `feedback feedback--${variante}`;
}

function enfocarEscaneo() {
  scanInput.focus();
}

function renderizar() {
  const orden = estado.orden;
  const resultados = estado.resultados || [];
  const total = orden.total || 0;

  nombreOrden.textContent = orden.cargada
    ? orden.filename || "Orden cargada"
    : "Ninguna orden cargada";

  detalleOrden.textContent = orden.cargada
    ? `${total} ítem${total === 1 ? "" : "s"} en la orden.` +
      (orden.ambiguos
        ? ` ${orden.ambiguos} terminación(es) de 4 dígitos son ambiguas.`
        : "")
    : "Selecciona el CSV de la orden para comenzar.";

  progreso.textContent = `${estado.escaneados} / ${total}`;
  resumenTabla.textContent = `${resultados.length} verificado${
    resultados.length === 1 ? "" : "s"
  }`;

  btnExportar.disabled = !estado.puede_exportar;
  btnReiniciar.disabled = !orden.cargada && resultados.length === 0;

  tablaResultados.replaceChildren(
    ...resultados.map((activo) => {
      const fila = document.createElement("tr");
      fila.append(
        crearCelda(activo.serial, "celda-codigo"),
        crearCelda(activo.brand),
        crearCelda(activo.model),
        crearCelda(activo.processor || "—"),
        crearCelda(activo.ram || "—"),
      );
      return fila;
    }),
  );

  tablaVacia.hidden = resultados.length > 0;
}

function mensajeSegunEstado() {
  if (estado.completada) {
    return ["¡Orden completada con éxito!", "complete"];
  }
  if (estado.orden.cargada) {
    return [
      `Orden lista · ${estado.escaneados} de ${estado.orden.total} verificados.`,
      "neutral",
    ];
  }
  return ["Carga una orden para comenzar", "idle"];
}

function crearEntradaNota(valor, campo, esSerial = false) {
  const entrada = document.createElement("input");
  entrada.type = "text";
  entrada.className = "entrada-tabla";
  if (esSerial) {
    entrada.classList.add("entrada-tabla--codigo");
    entrada.autocapitalize = "characters";
  }
  entrada.value = valor || "";
  entrada.dataset.campo = campo;
  entrada.autocomplete = "off";
  entrada.spellcheck = false;
  entrada.addEventListener("input", actualizarConfirmarNota);
  return entrada;
}

function crearFilaNota(item, serial) {
  const fila = document.createElement("tr");
  const celdaSerial = document.createElement("td");
  celdaSerial.append(crearEntradaNota(serial, "serial", true));
  fila.append(celdaSerial);

  const campos = [
    ["brand", item.marca],
    ["model", item.modelo],
    ["processor", item.procesador],
    ["ram", item.ram],
  ];
  for (const [campo, valor] of campos) {
    const celda = document.createElement("td");
    celda.append(crearEntradaNota(valor, campo));
    fila.append(celda);
  }
  return fila;
}

function renderizarAdvertenciasNota(datos) {
  const avisos = [...(datos.advertencias || [])];
  for (const item of datos.items || []) {
    const etiqueta = item.descripcion || "Producto sin descripción";
    for (const aviso of item.advertencias || []) {
      avisos.push(`${etiqueta}: ${aviso}`);
    }
  }

  const unicos = [...new Set(avisos)];
  advertenciasNota.replaceChildren(
    ...unicos.map((texto) => {
      const elemento = document.createElement("li");
      elemento.textContent = texto;
      return elemento;
    }),
  );
  advertenciasNota.hidden = unicos.length === 0;
}

function datosFilaNota(fila) {
  const datos = {};
  for (const entrada of fila.querySelectorAll("input[data-campo]")) {
    datos[entrada.dataset.campo] = entrada.value.trim();
  }
  return datos;
}

function filasNota() {
  return [...tablaNota.querySelectorAll("tr")];
}

function actualizarConfirmarNota() {
  if (revisionNota.hidden) {
    btnConfirmarNota.disabled = true;
    return;
  }

  const cantidad = filasNota().filter(
    (fila) => datosFilaNota(fila).serial,
  ).length;
  btnConfirmarNota.disabled = cantidad === 0 || ocupadoNota;
  estadoNota.hidden = false;
  estadoNota.textContent = cantidad
    ? `${cantidad} serial${cantidad === 1 ? "" : "es"} listo${
        cantidad === 1 ? "" : "s"
      } para cargar.`
    : "No hay seriales para cargar. Corrige la nota o usa el CSV de la orden.";
}

function limpiarRevisionNota() {
  revisionNota.hidden = true;
  tablaNota.replaceChildren();
  advertenciasNota.replaceChildren();
  advertenciasNota.hidden = true;
  estadoNota.hidden = true;
  estadoNota.textContent = "";
  btnConfirmarNota.disabled = true;
}

function renderizarNota(datos) {
  const items = Array.isArray(datos.items) ? datos.items : [];
  const filas = [];
  for (const item of items) {
    const seriales =
      Array.isArray(item.seriales) && item.seriales.length > 0
        ? item.seriales
        : [""];
    for (const serial of seriales) {
      filas.push({ item, serial });
    }
  }

  tablaNota.replaceChildren(
    ...filas.map(({ item, serial }) => crearFilaNota(item, serial)),
  );
  renderizarAdvertenciasNota(datos);
  revisionNota.hidden = false;
  actualizarConfirmarNota();
}

async function extraerNota() {
  const archivos = [...(archivoNota.files || [])];
  if (archivos.length === 0) {
    return;
  }

  const total = archivos.reduce((suma, archivo) => suma + archivo.size, 0);
  if (total > MAX_BYTES_NOTA) {
    const mensaje = "La nota supera el límite de 20 MB en total.";
    feedback(mensaje, "error");
    mostrarToast(mensaje, "error");
    archivoNota.value = "";
    return;
  }

  ocupadoNota = true;
  btnCargarNota.disabled = true;
  limpiarRevisionNota();
  estadoNota.hidden = false;
  estadoNota.textContent =
    archivos.length === 1
      ? "Leyendo la nota con OCR. Puede tardar unos segundos…"
      : `Leyendo ${archivos.length} páginas con OCR. Puede tardar unos segundos…`;
  feedback("Leyendo la nota de entrega…", "neutral");

  try {
    const datosFormulario = new FormData();
    for (const archivo of archivos) {
      datosFormulario.append("files", archivo);
    }

    const datos = await pedirJson("/api/nota/extraer", {
      method: "POST",
      body: datosFormulario,
    });

    renderizarNota(datos);
    const seriales = datos.seriales_total || 0;
    feedback(
      seriales > 0
        ? "Revisa la nota extraída y confirma la orden."
        : "No se detectaron seriales en la nota. Revisa el archivo o usa el CSV.",
      seriales > 0 ? "neutral" : "warning",
    );
  } catch (error) {
    limpiarRevisionNota();
    estadoNota.hidden = false;
    estadoNota.textContent = error.message;
    feedback(error.message, "error");
    mostrarToast(error.message, "error");
  } finally {
    archivoNota.value = "";
    ocupadoNota = false;
    btnCargarNota.disabled = false;
    actualizarConfirmarNota();
    enfocarEscaneo();
  }
}

function campoCsv(valor) {
  return `"${String(valor ?? "").replace(/"/g, '""')}"`;
}

function construirCsvNota(filas) {
  const encabezados = ["serial", "brand", "model", "processor", "ram"];
  return [
    encabezados.map(campoCsv).join(","),
    ...filas.map((fila) =>
      encabezados.map((campo) => campoCsv(fila[campo])).join(","),
    ),
  ].join("\r\n");
}

async function confirmarNota() {
  if (ocupadoNota) {
    return;
  }

  const filas = filasNota()
    .map(datosFilaNota)
    .filter((fila) => fila.serial)
    .map((fila) => ({ ...fila, serial: fila.serial.toUpperCase() }));

  if (filas.length === 0) {
    feedback("No hay seriales para cargar.", "error");
    return;
  }

  const vistos = new Set();
  for (const fila of filas) {
    if (vistos.has(fila.serial)) {
      const mensaje = `El S/N ${fila.serial} está repetido en la revisión.`;
      feedback(mensaje, "error");
      mostrarToast(mensaje, "error");
      return;
    }
    vistos.add(fila.serial);
  }

  ocupadoNota = true;
  btnConfirmarNota.disabled = true;
  btnCargarNota.disabled = true;
  feedback("Cargando la orden generada desde la nota…", "neutral");

  try {
    const contenido = construirCsvNota(filas);
    const archivo = new Blob([contenido], { type: "text/csv;charset=utf-8" });
    const datosFormulario = new FormData();
    datosFormulario.append("file", archivo, "orden-nota.csv");

    const datos = await pedirJson("/api/validacion/orden", {
      method: "POST",
      body: datosFormulario,
    });

    estado = datos.estado;
    renderizar();
    limpiarRevisionNota();
    feedback(datos.mensaje, "neutral");
    mostrarToast("Orden generada desde la nota.", "ok");
  } catch (error) {
    feedback(error.message, "error");
    mostrarToast(error.message, "error");
  } finally {
    ocupadoNota = false;
    btnCargarNota.disabled = false;
    actualizarConfirmarNota();
    enfocarEscaneo();
  }
}

async function cargarEstado() {
  try {
    estado = await pedirJson("/api/validacion/estado");
    renderizar();
    const [mensaje, variante] = mensajeSegunEstado();
    feedback(mensaje, variante);
  } catch (error) {
    feedback("No se pudo conectar con el servidor.", "error");
    console.error("Estado de validación:", error);
  } finally {
    enfocarEscaneo();
  }
}

async function procesarCodigo(codigo) {
  if (ocupado) {
    return;
  }

  const limpio = (codigo || "").trim();
  if (!limpio) {
    enfocarEscaneo();
    return;
  }

  ocupado = true;
  btnEscanear.disabled = true;

  try {
    const datos = await pedirJson("/api/validacion/escanear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: limpio }),
    });

    if (datos.evento === "ambiguo") {
      scanInput.value = limpio;
      scanInput.setSelectionRange(0, limpio.length);
    } else {
      scanInput.value = "";
    }
    estado = datos.estado;
    renderizar();

    switch (datos.evento) {
      case "verificado":
        feedback(
          datos.completada ? "¡Orden completada con éxito!" : datos.mensaje,
          datos.completada ? "complete" : "ok",
        );
        if (datos.completada) {
          mostrarToast("Orden completada. Ya puedes exportar el reporte.", "ok");
        }
        break;
      case "ambiguo":
        feedback(datos.mensaje, "warning");
        break;
      case "duplicado":
        feedback(datos.mensaje, "warning");
        break;
      case "fuera_de_orden":
        feedback(datos.mensaje, "error");
        break;
      default:
        feedback(datos.mensaje, "idle");
        break;
    }
  } catch (error) {
    feedback(error.message, "error");
  } finally {
    ocupado = false;
    btnEscanear.disabled = false;
    enfocarEscaneo();
  }
}

function escanear() {
  const codigo = scanInput.value.trim();
  if (!codigo) {
    enfocarEscaneo();
    return;
  }
  procesarCodigo(codigo);
}

async function subirOrden() {
  const archivo = archivoOrden.files?.[0];
  if (!archivo) {
    return;
  }

  const datosFormulario = new FormData();
  datosFormulario.append("file", archivo);

  btnCargar.disabled = true;
  feedback("Leyendo la orden…", "neutral");

  try {
    const datos = await pedirJson("/api/validacion/orden", {
      method: "POST",
      body: datosFormulario,
    });

    estado = datos.estado;
    renderizar();
    feedback(datos.mensaje, "neutral");
    mostrarToast("Orden cargada correctamente.", "ok");
  } catch (error) {
    feedback(error.message, "error");
    mostrarToast(error.message, "error");
  } finally {
    archivoOrden.value = "";
    btnCargar.disabled = false;
    enfocarEscaneo();
  }
}

async function reiniciar() {
  if (
    estado &&
    (estado.orden.cargada || estado.resultados.length > 0) &&
    !window.confirm("¿Descartar la orden y los resultados de esta validación?")
  ) {
    return;
  }

  try {
    const datos = await pedirJson("/api/validacion/reiniciar", {
      method: "POST",
    });
    estado = datos.estado;
    scanInput.value = "";
    renderizar();
    feedback("Carga una orden para comenzar", "idle");
  } catch (error) {
    feedback(error.message, "error");
  } finally {
    enfocarEscaneo();
  }
}

btnCargar.addEventListener("click", () => archivoOrden.click());
archivoOrden.addEventListener("change", subirOrden);
btnCargarNota.addEventListener("click", () => archivoNota.click());
archivoNota.addEventListener("change", extraerNota);
btnConfirmarNota.addEventListener("click", confirmarNota);
btnCancelarNota.addEventListener("click", () => {
  limpiarRevisionNota();
  if (estado) {
    const [mensaje, variante] = mensajeSegunEstado();
    feedback(mensaje, variante);
  } else {
    feedback("Revisión de la nota cancelada.", "idle");
  }
  enfocarEscaneo();
});
btnEscanear.addEventListener("click", escanear);
btnReiniciar.addEventListener("click", reiniciar);

scanInput.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter") {
    evento.preventDefault();
    escanear();
  }
});

btnExportar.addEventListener("click", () => {
  if (!estado?.puede_exportar) {
    return;
  }
  window.location.assign("/api/validacion/exportar");
});

document.getElementById("btn-salir")?.addEventListener("click", cerrarSesion);

verificarServidor(estadoServidor);
cargarEstado();
