const estadoServidor = document.getElementById("estado-servidor");

async function verificarServidor() {
  try {
    const respuesta = await fetch("/api/health");
    if (!respuesta.ok) {
      throw new Error(`HTTP ${respuesta.status}`);
    }

    const datos = await respuesta.json();
    estadoServidor.textContent = `Servidor OK · v${datos.version}`;
    estadoServidor.className = "estado estado--ok";
  } catch (error) {
    estadoServidor.textContent = "Sin conexión con el servidor";
    estadoServidor.className = "estado estado--error";
    console.error("Health check:", error);
  }
}

verificarServidor();
