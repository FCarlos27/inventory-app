const formulario = document.getElementById("form-login");
const inputClave = document.getElementById("clave");
const errorEl = document.getElementById("login-error");
const boton = formulario.querySelector("button[type='submit']");

function mostrarError(mensaje) {
  errorEl.textContent = mensaje;
  errorEl.hidden = false;
}

formulario.addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const clave = inputClave.value.trim();
  if (!clave) {
    mostrarError("Ingresa la clave de acceso.");
    return;
  }

  boton.disabled = true;
  errorEl.hidden = true;

  try {
    const respuesta = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clave }),
    });
    const datos = await respuesta.json().catch(() => ({}));

    if (!respuesta.ok) {
      mostrarError(datos.detail || "No se pudo iniciar sesión.");
      inputClave.select();
      return;
    }

    window.location.href = "/";
  } catch (error) {
    mostrarError("No se pudo conectar con el servidor.");
    console.error("Login:", error);
  } finally {
    boton.disabled = false;
  }
});
