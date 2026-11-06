const ESTADOS = {
  apagada: { texto: "Apagada", clase: "estado--pendiente" },
  iniciando: { texto: "Iniciando…", clase: "estado--pendiente" },
  activa: { texto: "Cámara activa", clase: "estado--ok" },
  deteniendo: { texto: "Deteniendo…", clase: "estado--pendiente" },
  error: { texto: "Error de cámara", clase: "estado--error" },
};

const PAUSA_MS = 2200;
const AYUDA_ESCANEO =
  "Apunta al código de barras o QR. La detección es automática.";

function mensajeError(error) {
  const detalle = [
    error?.name,
    typeof error === "string" ? error : error?.message,
  ]
    .filter(Boolean)
    .join(" ");

  if (/NotAllowedError|PermissionDeniedError|Permission denied/i.test(detalle)) {
    return "Permiso de cámara denegado. Habilítalo desde el navegador.";
  }
  if (/NotFoundError|DevicesNotFoundError|device not found/i.test(detalle)) {
    return "No se encontró ninguna cámara disponible en este dispositivo.";
  }
  if (/NotReadableError|TrackStartError|start video source/i.test(detalle)) {
    return "La cámara está siendo usada por otra aplicación.";
  }
  if (/OverconstrainedError/i.test(detalle)) {
    return "La cámara no soporta la configuración solicitada.";
  }

  return "No se pudo iniciar la cámara.";
}

function formatearZoom(valor) {
  return `${Number(valor).toFixed(1)}×`;
}

export function configurarCamara({ alDetectar, pausaMs = PAUSA_MS } = {}) {
  const lector = document.getElementById("lector-camara");
  const estadoEl = document.getElementById("camara-estado");
  const ayudaEl = document.getElementById("camara-ayuda");
  const btnActivar = document.getElementById("btn-camara-activar");
  const btnDetener = document.getElementById("btn-camara-detener");
  const zoomContenedor = document.getElementById("camara-zoom");
  const zoomInput = document.getElementById("camara-zoom-input");
  const zoomValor = document.getElementById("camara-zoom-valor");
  const confirmacion = document.getElementById("camara-confirmacion");
  const codigoEl = document.getElementById("camara-codigo");
  const btnConfirmar = document.getElementById("btn-camara-confirmar");
  const btnDescartar = document.getElementById("btn-camara-descartar");

  if (!lector || !estadoEl || !ayudaEl || !btnActivar || !btnDetener) {
    return {
      iniciar: async () => {},
      detener: async () => {},
      get activa() {
        return false;
      },
    };
  }

  const usaConfirmacion = Boolean(
    confirmacion && codigoEl && btnConfirmar && btnDescartar,
  );
  const estadoPausado = window.Html5QrcodeScannerState?.PAUSED ?? 3;

  let instancia = null;
  let activa = false;
  let cambiando = false;
  let pausado = false;
  let pausaTimer = null;
  let overlayPausa = null;
  let caracteristicaZoom = null;
  let codigoPendiente = null;

  function pintarEstado(nombre, mensaje) {
    const definicion = ESTADOS[nombre] || ESTADOS.apagada;
    estadoEl.textContent = definicion.texto;
    estadoEl.className = `estado ${definicion.clase}`;
    if (mensaje) {
      ayudaEl.textContent = mensaje;
    }
  }

  function bloquear(bloqueado) {
    btnActivar.disabled = bloqueado;
    btnDetener.disabled = bloqueado;
  }

  function limpiarLector() {
    lector.replaceChildren();
    overlayPausa = null;
  }

  function prepararOverlayPausa() {
    overlayPausa = [...lector.querySelectorAll("div")].find(
      (nodo) => nodo.textContent.trim() === "Scanner paused",
    );

    if (overlayPausa) {
      overlayPausa.classList.add("camara-pausa");
      overlayPausa.textContent = "Código detectado";
    }
  }

  function mostrarConfirmacion(codigo) {
    if (!usaConfirmacion) {
      return;
    }
    codigoPendiente = codigo;
    codigoEl.textContent = codigo;
    confirmacion.hidden = false;
    btnConfirmar.focus();
  }

  function ocultarConfirmacion() {
    codigoPendiente = null;
    if (usaConfirmacion) {
      confirmacion.hidden = true;
    }
  }

  function enviar(codigo) {
    Promise.resolve(alDetectar?.(codigo)).catch((error) => {
      console.error("Procesar código de cámara:", error);
    });
  }

  function reanudar() {
    pausaTimer = null;
    ocultarConfirmacion();

    if (!activa || !instancia || !pausado) {
      return;
    }

    try {
      instancia.resume();
      ayudaEl.textContent = AYUDA_ESCANEO;
    } catch (error) {
      console.error("Reanudar cámara:", error);
    } finally {
      pausado = false;
    }
  }

  function pausar(codigo) {
    if (!activa || !instancia || pausado) {
      return;
    }

    pausado = true;
    clearTimeout(pausaTimer);
    pausaTimer = null;

    try {
      instancia.pause();
    } catch (error) {
      console.error("Pausar cámara:", error);
      pausado = false;
      return;
    }

    if (overlayPausa) {
      overlayPausa.textContent = usaConfirmacion
        ? "Esperando confirmación…"
        : `Código detectado: ${codigo}`;
    }

    if (usaConfirmacion) {
      mostrarConfirmacion(codigo);
      ayudaEl.textContent =
        "Revisa el código y confirma para enviarlo o vuelve a escanear.";
      return;
    }

    ayudaEl.textContent = "Código detectado. Enviando…";
    enviar(codigo);
    pausaTimer = setTimeout(reanudar, pausaMs);
  }

  function confirmar() {
    if (!codigoPendiente) {
      return;
    }

    const codigo = codigoPendiente;
    ocultarConfirmacion();
    ayudaEl.textContent = "Código confirmado. Enviando…";
    enviar(codigo);
    clearTimeout(pausaTimer);
    pausaTimer = setTimeout(reanudar, pausaMs);
  }

  function descartar() {
    reanudar();
  }

  function reiniciarZoom() {
    caracteristicaZoom = null;
    if (zoomContenedor) {
      zoomContenedor.hidden = true;
    }
    if (zoomInput) {
      zoomInput.value = "1";
    }
    if (zoomValor) {
      zoomValor.textContent = formatearZoom(1);
    }
  }

  function configurarZoom() {
    if (!zoomContenedor || !zoomInput || !zoomValor || !instancia) {
      return;
    }

    try {
      const caracteristica = instancia
        .getRunningTrackCameraCapabilities()
        .zoomFeature();

      if (!caracteristica?.isSupported()) {
        return;
      }

      const minimo = caracteristica.min();
      const maximo = caracteristica.max();
      if (!(maximo > minimo)) {
        return;
      }

      const paso =
        caracteristica.step() || Math.max((maximo - minimo) / 10, 0.1);

      zoomInput.min = String(minimo);
      zoomInput.max = String(maximo);
      zoomInput.step = String(paso);
      zoomInput.value = String(minimo);
      zoomValor.textContent = formatearZoom(minimo);
      zoomContenedor.hidden = false;
      caracteristicaZoom = caracteristica;
    } catch (error) {
      console.error("Zoom de cámara:", error);
    }
  }

  function alLeer(texto) {
    if (!activa || pausado) {
      return;
    }

    const codigo = (texto || "").trim();
    if (!codigo) {
      return;
    }

    pausar(codigo);
  }

  async function iniciar() {
    if (activa || cambiando) {
      return;
    }

    if (!window.isSecureContext) {
      pintarEstado(
        "error",
        "La cámara requiere HTTPS o abrir la app desde localhost.",
      );
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      pintarEstado(
        "error",
        "Este navegador no permite acceder a la cámara.",
      );
      return;
    }

    if (typeof window.Html5Qrcode === "undefined") {
      pintarEstado(
        "error",
        "No se pudo cargar Html5-Qrcode. Revisa la conexión a internet.",
      );
      return;
    }

    cambiando = true;
    bloquear(true);
    pintarEstado("iniciando", "Solicitando permiso de cámara…");
    lector.hidden = false;
    limpiarLector();

    try {
      instancia = new window.Html5Qrcode("lector-camara", {
        verbose: false,
        useBarCodeDetectorIfSupported: true,
      });

      const formatos = [
        window.Html5QrcodeSupportedFormats?.CODE_128,
        window.Html5QrcodeSupportedFormats?.CODE_39,
        window.Html5QrcodeSupportedFormats?.QR_CODE,
      ].filter((formato) => formato !== undefined);

      const configuracion = {
        fps: 10,
        qrbox: (ancho, alto) => ({
          // Rectángulo ancho: favorece los códigos de barras CODE_128 y CODE_39.
          width: Math.floor(ancho * 0.85),
          height: Math.floor(alto * 0.4),
        }),
        aspectRatio: 1.7778,
        disableFlip: false,
        videoConstraints: {
          facingMode: "environment",
          width: { ideal: 1280 },
          height: { ideal: 720 },
          focusMode: "continuous",
        },
      };

      if (formatos.length > 0) {
        configuracion.formatsToSupport = formatos;
      }

      await instancia.start(
        { facingMode: "environment" },
        configuracion,
        alLeer,
        () => {},
      );

      activa = true;
      prepararOverlayPausa();
      configurarZoom();
      btnActivar.hidden = true;
      btnDetener.hidden = false;
      pintarEstado("activa", AYUDA_ESCANEO);
    } catch (error) {
      console.error("Iniciar cámara:", error);

      if (instancia) {
        try {
          await instancia.stop();
        } catch {
          // La cámara pudo no haber llegado a iniciar.
        }
        try {
          instancia.clear();
        } catch {
          // Sin interfaz que limpiar.
        }
      }

      instancia = null;
      activa = false;
      lector.hidden = true;
      limpiarLector();
      reiniciarZoom();
      btnActivar.hidden = false;
      btnDetener.hidden = true;
      pintarEstado("error", mensajeError(error));
    } finally {
      cambiando = false;
      bloquear(false);
    }
  }

  async function detener() {
    if (!activa || cambiando) {
      return;
    }

    cambiando = true;
    bloquear(true);
    pintarEstado("deteniendo", "Apagando la cámara…");
    clearTimeout(pausaTimer);
    pausaTimer = null;
    ocultarConfirmacion();

    try {
      if (instancia && instancia.getState() === estadoPausado) {
        instancia.resume();
      }
      if (instancia) {
        await instancia.stop();
      }
    } catch (error) {
      console.error("Detener cámara:", error);
    } finally {
      instancia = null;
      activa = false;
      pausado = false;
      cambiando = false;
      lector.hidden = true;
      limpiarLector();
      reiniciarZoom();
      btnActivar.hidden = false;
      btnDetener.hidden = true;
      bloquear(false);
      pintarEstado(
        "apagada",
        "Activa la cámara para escanear con la tablet.",
      );
    }
  }

  zoomInput?.addEventListener("input", () => {
    const valor = Number(zoomInput.value);
    if (zoomValor) {
      zoomValor.textContent = formatearZoom(valor);
    }
    try {
      caracteristicaZoom?.apply(valor);
    } catch (error) {
      console.error("Aplicar zoom:", error);
    }
  });

  btnConfirmar?.addEventListener("click", confirmar);
  btnDescartar?.addEventListener("click", descartar);
  btnActivar.addEventListener("click", iniciar);
  btnDetener.addEventListener("click", detener);

  window.addEventListener("pagehide", () => {
    clearTimeout(pausaTimer);
    ocultarConfirmacion();
    if (!activa || !instancia) {
      return;
    }
    try {
      if (instancia.getState() === estadoPausado) {
        instancia.resume();
      }
      instancia.stop().catch(() => {});
    } catch {
      // La página se está cerrando.
    }
  });

  return {
    iniciar,
    detener,
    get activa() {
      return activa;
    },
  };
}
