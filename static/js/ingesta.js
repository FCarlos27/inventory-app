import {
  crearCelda,
  mostrarToast,
  pedirJson,
  verificarServidor,
} from "./common.js";
import { configurarCamara } from "./camara.js";

const estadoServidor = document.getElementById("estado-servidor");
const contador = document.getElementById("contador");
const feedbackEl = document.getElementById("feedback");
const scanInput = document.getElementById("scan-input");
const btnEscanear = document.getElementById("btn-escanear");
const btnCancelar = document.getElementById("btn-cancelar");
const btnReiniciar = document.getElementById("btn-reiniciar");
const btnExportar = document.getElementById("btn-exportar");
const pistaEscaneo = document.getElementById("pista-escaneo");
const tablaActivos = document.getElementById("tabla-activos");
const tablaVacia = document.getElementById("tabla-vacia");
const resumenTabla = document.getElementById("resumen-tabla");

const modal = document.getElementById("modal-modelo");
const formModelo = document.getElementById("form-modelo");
const modalPn = document.getElementById("modal-pn");
const modalSerial = document.getElementById("modal-serial");
const modalMarca = document.getElementById("modal-marca");
const modalModelo = document.getElementById("modal-modelo-input");
const modalError = document.getElementById("modal-error");
const btnGuardarModelo = document.getElementById("btn-guardar-modelo");
const btnOmitir = document.getElementById("btn-omitir");
const btnCancelarCaptura = document.getElementById("btn-cancelar-captura");

let estado = null;
let ocupado = false;
let camara = null;

function feedback(mensaje, variante = "neutral") {
  feedbackEl.textContent = mensaje;
  feedbackEl.className = `feedback feedback--${variante}`;
}

function normalizarCodigo(texto) {
  return (texto || "").trim().toUpperCase();
}

function enfocarEscaneo() {
  if (modal.open || camara?.activa) {
    return;
  }
  scanInput.focus();
}

function mostrarErrorModal(mensaje) {
  modalError.textContent = mensaje;
  modalError.hidden = false;
}

function abrirModal(necesita) {
  if (modal.open) {
    return;
  }

  modalPn.textContent = necesita.p_n;
  modalSerial.textContent = necesita.serial;
  modalMarca.value = "";
  modalModelo.value = "";
  modalError.hidden = true;

  modal.showModal();
  modalMarca.focus();
}

function cerrarModal() {
  if (modal.open) {
    modal.close();
  }
}

function renderizar() {
  const activos = estado.activos || [];
  const pendiente = estado.pendiente;

  contador.textContent = `Equipos: ${estado.total}`;
  resumenTabla.textContent = `${activos.length} activo${
    activos.length === 1 ? "" : "s"
  }`;

  btnExportar.disabled = !estado.puede_exportar;
  btnCancelar.disabled = !estado.puede_cancelar;

  if (pendiente) {
    scanInput.placeholder = "Escanea el P/N y presiona Enter";
    pistaEscaneo.textContent = pendiente.p_n
      ? `S/N ${pendiente.serial} capturado · P/N ${pendiente.p_n}.`
      : `S/N ${pendiente.serial} capturado. Escanea el P/N.`;
  } else {
    scanInput.placeholder = "Escanea el S/N y presiona Enter";
    pistaEscaneo.textContent = "Escanea el S/N del equipo.";
  }

  tablaActivos.replaceChildren(
    ...activos.map((activo) => {
      const fila = document.createElement("tr");
      fila.append(
        crearCelda(activo.serial, "celda-codigo"),
        crearCelda(activo.p_n, "celda-codigo"),
        crearCelda(activo.brand),
        crearCelda(activo.model),
        crearCelda(activo.status, "celda-estado"),
      );
      return fila;
    }),
  );

  tablaVacia.hidden = activos.length > 0;

  if (estado.necesita_modelo) {
    abrirModal(estado.necesita_modelo);
  } else {
    cerrarModal();
  }
}

function mensajeSegunEstado() {
  if (estado.necesita_modelo) {
    return ["P/N nuevo: ingresa marca y modelo.", "warning"];
  }
  if (estado.pendiente) {
    return ["S/N capturado. Escanea el P/N.", "neutral"];
  }
  if (estado.total > 0) {
    return [
      `${estado.total} activo${estado.total === 1 ? "" : "s"} registrado${
        estado.total === 1 ? "" : "s"
      } en esta sesión.`,
      "neutral",
    ];
  }
  return ["Escanea el S/N del equipo", "neutral"];
}

async function cargarEstado() {
  try {
    estado = await pedirJson("/api/ingesta/estado");
    renderizar();
    const [mensaje, variante] = mensajeSegunEstado();
    feedback(mensaje, variante);
  } catch (error) {
    feedback("No se pudo conectar con el servidor.", "error");
    console.error("Estado de ingesta:", error);
  } finally {
    enfocarEscaneo();
  }
}

async function procesarCodigo(codigo, desdeCamara = false) {
  if (ocupado) {
    return;
  }

  const limpio = normalizarCodigo(codigo);
  if (!limpio) {
    enfocarEscaneo();
    return;
  }

  if (desdeCamara) {
    if (modal.open) {
      return;
    }
    if (
      estado?.pendiente &&
      limpio === normalizarCodigo(estado.pendiente.serial)
    ) {
      feedback("Ese S/N ya fue capturado. Escanea el P/N.", "warning");
      return;
    }
  }

  ocupado = true;
  btnEscanear.disabled = true;

  try {
    const datos = await pedirJson("/api/ingesta/escanear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo: limpio }),
    });

    scanInput.value = "";
    estado = datos.estado;
    renderizar();

    switch (datos.evento) {
      case "sn_capturado":
        feedback(datos.mensaje, "neutral");
        break;
      case "requiere_modelo":
        feedback(datos.mensaje, "warning");
        break;
      case "registrado":
        feedback(datos.mensaje, "ok");
        mostrarToast(datos.mensaje, "ok");
        break;
      case "duplicado":
        feedback(datos.mensaje, "warning");
        break;
      default:
        feedback(datos.mensaje, "neutral");
        break;
    }
  } catch (error) {
    feedback(error.message, "error");
  } finally {
    ocupado = false;
    btnEscanear.disabled = false;
    scanInput.value = "";
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

async function enviarModelo(payload) {
  btnGuardarModelo.disabled = true;
  btnOmitir.disabled = true;

  try {
    const datos = await pedirJson("/api/ingesta/modelo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    estado = datos.estado;
    renderizar();
    feedback(datos.mensaje, "ok");
    mostrarToast(datos.mensaje, "ok");
  } catch (error) {
    if (modal.open) {
      mostrarErrorModal(error.message);
    } else {
      feedback(error.message, "error");
    }
  } finally {
    btnGuardarModelo.disabled = false;
    btnOmitir.disabled = false;
    enfocarEscaneo();
  }
}

async function cancelarPendiente() {
  if (!estado?.puede_cancelar) {
    cerrarModal();
    return;
  }

  try {
    const datos = await pedirJson("/api/ingesta/cancelar", {
      method: "POST",
    });
    estado = datos.estado;
    scanInput.value = "";
    renderizar();
    feedback(datos.mensaje, "neutral");
  } catch (error) {
    feedback(error.message, "error");
  } finally {
    enfocarEscaneo();
  }
}

async function reiniciar() {
  if (
    estado &&
    estado.total > 0 &&
    !window.confirm("¿Reiniciar la sesión y descartar los activos capturados?")
  ) {
    return;
  }

  try {
    const datos = await pedirJson("/api/ingesta/reiniciar", {
      method: "POST",
    });
    estado = datos.estado;
    scanInput.value = "";
    cerrarModal();
    renderizar();
    feedback("Sesión reiniciada. Escanea el S/N del equipo", "neutral");
  } catch (error) {
    feedback(error.message, "error");
  } finally {
    enfocarEscaneo();
  }
}

btnEscanear.addEventListener("click", escanear);
btnCancelar.addEventListener("click", cancelarPendiente);
btnReiniciar.addEventListener("click", reiniciar);
btnCancelarCaptura.addEventListener("click", cancelarPendiente);

scanInput.addEventListener("keydown", (evento) => {
  if (evento.key === "Enter") {
    evento.preventDefault();
    escanear();
  }
});

formModelo.addEventListener("submit", (evento) => {
  evento.preventDefault();

  if (!estado?.necesita_modelo) {
    cerrarModal();
    return;
  }

  const marca = modalMarca.value.trim();
  if (!marca) {
    mostrarErrorModal("La marca es obligatoria para agregar el P/N.");
    modalMarca.focus();
    return;
  }

  enviarModelo({
    p_n: estado.necesita_modelo.p_n,
    brand: marca,
    model: modalModelo.value.trim(),
  });
});

btnOmitir.addEventListener("click", () => {
  if (!estado?.necesita_modelo) {
    cerrarModal();
    return;
  }

  enviarModelo({ p_n: estado.necesita_modelo.p_n, omitir: true });
});

modal.addEventListener("cancel", (evento) => {
  evento.preventDefault();
  cancelarPendiente();
});

document.addEventListener("keydown", (evento) => {
  if (evento.key !== "Escape" || modal.open) {
    return;
  }
  if (!estado?.puede_cancelar) {
    return;
  }
  evento.preventDefault();
  cancelarPendiente();
});

btnExportar.addEventListener("click", () => {
  if (!estado?.puede_exportar) {
    return;
  }
  window.location.assign("/api/ingesta/exportar");
});

camara = configurarCamara({
  alDetectar: (codigo) => procesarCodigo(codigo, true),
});

verificarServidor(estadoServidor);
cargarEstado();
