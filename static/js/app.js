import { cerrarSesion, verificarServidor } from "./common.js";

verificarServidor(document.getElementById("estado-servidor"));
document.getElementById("btn-salir")?.addEventListener("click", cerrarSesion);
