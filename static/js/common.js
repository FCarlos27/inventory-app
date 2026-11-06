const TIPOS_TOAST = new Set(["info", "ok", "warning", "error"]);
let temporizadorToast = null;
let temporizadorOcultar = null;

export async function verificarServidor(elemento) {
  if (!elemento) {
    return;
  }

  try {
    const respuesta = await fetch("/api/health", { cache: "no-store" });
    if (!respuesta.ok) {
      throw new Error(`HTTP ${respuesta.status}`);
    }

    const datos = await respuesta.json();
    elemento.textContent = `Servidor OK · v${datos.version}`;
    elemento.className = "estado estado--ok";
  } catch (error) {
    elemento.textContent = "Sin conexión con el servidor";
    elemento.className = "estado estado--error";
    console.error("Health check:", error);
  }
}

function textoError(datos, respuesta) {
  const detalle = datos?.detail;

  if (typeof detalle === "string" && detalle) {
    return detalle;
  }

  if (Array.isArray(detalle)) {
    const mensajes = detalle
      .map((item) => item?.msg)
      .filter((mensaje) => typeof mensaje === "string");
    if (mensajes.length > 0) {
      return mensajes.join(" ");
    }
  }

  return `Error HTTP ${respuesta.status}`;
}

export async function pedirJson(url, opciones = {}) {
  const respuesta = await fetch(url, { cache: "no-store", ...opciones });

  if (respuesta.status === 401) {
    window.location.assign("/login");
    throw new Error("La sesión venció. Vuelve a ingresar la clave.");
  }

  const tipo = respuesta.headers.get("content-type") || "";

  let datos = null;
  if (tipo.includes("application/json")) {
    datos = await respuesta.json().catch(() => null);
  }

  if (!respuesta.ok) {
    throw new Error(textoError(datos, respuesta));
  }

  return datos;
}

export async function cerrarSesion() {
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch (error) {
    console.error("Cierre de sesión:", error);
  }
  window.location.assign("/login");
}

export function crearCelda(texto, clase = "") {
  const celda = document.createElement("td");
  celda.textContent = texto ?? "";
  if (clase) {
    celda.className = clase;
  }
  return celda;
}

export function mostrarToast(mensaje, tipo = "info") {
  const toast = document.getElementById("toast");
  if (!toast) {
    return;
  }

  const variante = TIPOS_TOAST.has(tipo) ? tipo : "info";
  toast.textContent = mensaje;
  toast.className = `toast toast--${variante} toast--visible`;
  toast.hidden = false;

  clearTimeout(temporizadorToast);
  clearTimeout(temporizadorOcultar);
  temporizadorToast = setTimeout(() => {
    toast.classList.remove("toast--visible");
    temporizadorOcultar = setTimeout(() => {
      toast.hidden = true;
    }, 200);
  }, 3200);
}
