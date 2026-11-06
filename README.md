# Inventario Depósito

Aplicación web local para validar la entrega de equipos de una orden usando
los últimos 4 dígitos del S/N. Está pensada para tablets con teclado o pistola
lectora USB, y se sirve desde una Mac en la red local por HTTP.

Versión actual: `0.4.0`.

## Estado del MVP

- Solo está disponible el modo **Validación de orden**.
- La ingesta y la carga manual de la orden por CSV están deshabilitadas y
  ocultas en la interfaz.
- La orden se genera a partir de la nota de entrega, con revisión y
  confirmación humana.

## Funcionalidades

### Acceso

- Clave compartida obligatoria, porque la Wi-Fi es compartida.
- La clave se lee de `data/clave.txt` (permisos `600`) o de la variable de
  entorno `INVENTARIO_CLAVE`.
- Cookie de acceso `HttpOnly`, tokens en memoria con vigencia de 12 horas.
- Bloqueo temporal tras 5 intentos fallidos por IP en 5 minutos.
- Botón **Mostrar / Ocultar** la clave en el formulario de acceso.

### Nota de entrega

- Carga de una o más fotos (JPG/PNG) o PDF, hasta 20 MB en total y 20 páginas.
- PDF digital: extracción de texto con `pypdfium2`.
- Fotos y PDF escaneados: OCR con Tesseract en español e inglés (`spa+eng`).
- Reconoce marca, modelo, procesador, RAM, cantidades y seriales.
- Une grupos de equipos que continúan en la página siguiente.
- Muestra una vista previa editable con advertencias antes de continuar.
- **Completar campos vacíos**: copia el valor no vacío más cercano hacia
  arriba; si no existe, hacia abajo. Solo considera filas con S/N.
- Las filas sin S/N se omiten al generar la orden.
- La orden solo se carga después de presionar **Confirmar y cargar orden**.

### Validación

- Escaneo por los últimos 4 dígitos del S/N, con `Enter` o pistola USB.
- Si hay más de una coincidencia, solicita el S/N completo.
- Detecta S/N fuera de la orden, duplicados y terminaciones ambiguas.
- Muestra el progreso (`verificados / total`) y la tabla de S/N verificados.
- **Nueva validación** descarta la orden y los resultados de la sesión.

### Exportación

- El CSV se puede exportar desde el primer S/N verificado, aunque la orden
  esté incompleta.
- Columnas en español: `S/N`, `Marca`, `Modelo`, `Procesador`, `RAM`.
- Incluye BOM para abrir correctamente en Excel.
- La descarga permanece en la misma página y muestra un aviso de éxito o error.

## Flujo recomendado

1. Abrir la aplicación e ingresar la clave de acceso.
2. Cargar la nota de entrega (foto o PDF).
3. Revisar la tabla extraída, corregir o completar campos y confirmar.
4. Escanear cada equipo con los últimos 4 dígitos de su S/N.
5. Exportar el CSV de verificación.

## Requisitos

- Python 3.11 o superior.
- Tesseract 5 con los idiomas `spa` y `eng` instalados.
  - En macOS: `brew install tesseract tesseract-lang`
  - Verificar: `tesseract --list-langs`

Dependencias de Python: ver `requirements.txt` (`fastapi`, `uvicorn`,
`python-multipart`, `Pillow`, `pypdfium2`).

## Ejecución local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Abrir desde la tablet o el equipo en la misma red:

```text
http://carloss-macbook-air.local:8000/
```

Si el nombre `.local` no resuelve, usar la IP actual de la Mac, por ejemplo
`http://172.18.50.208:8000/`.

La aplicación usa HTTP, no HTTPS. Al reiniciar el servidor se cierran las
sesiones y hay que volver a ingresar la clave.

## Estructura del proyecto

```text
main.py                 Arranque, middleware, seguridad y routers
routers/                Endpoints de acceso, sistema, nota y validación
services/               Lógica de acceso, sesiones, nota y validación
static/                 Páginas HTML, JavaScript y CSS
data/                   Clave local y catálogo de modelos
requirements.txt        Dependencias de Python
```

## API principal

| Método | Ruta | Descripción |
| --- | --- | --- |
| `POST` | `/api/login` | Ingresa con la clave compartida |
| `POST` | `/api/logout` | Cierra la sesión |
| `GET` | `/api/health` | Estado del servidor |
| `POST` | `/api/nota/extraer` | Extrae datos de la nota |
| `GET` | `/api/validacion/estado` | Estado de la validación |
| `POST` | `/api/validacion/orden` | Carga la orden desde la nota |
| `POST` | `/api/validacion/escanear` | Verifica un S/N |
| `POST` | `/api/validacion/reiniciar` | Reinicia la validación |
| `GET` | `/api/validacion/exportar` | Descarga el CSV |

## Seguridad y datos

- Las sesiones viven en memoria: al reiniciar el servidor se pierden.
- Cada navegador tiene su propia orden y sus propios resultados.
- Se aplican límites de tamaño de archivo y cabeceras de seguridad (CSP,
  `X-Frame-Options`, `nosniff`, entre otras).
- `data/clave.txt` y los certificados locales están excluidos de Git.

## Limitaciones conocidas

- No se usa cámara; el ingreso es manual o con pistola USB.
- El OCR depende de la calidad de la foto. Las marcas de lapicero pueden
  agregar caracteres, y los seriales HP de más de 10 caracteres se recortan
  con una advertencia.
- **Completar campos vacíos** usa el valor más cercano. Si un bloque vacío
  queda entre dos modelos distintos, conviene revisar la tabla antes de
  confirmar.
- La orden y los resultados no se guardan en disco.
- La IP por DHCP puede cambiar. El nombre `carloss-macbook-air.local`
  funciona en la tablet; todavía no se pidió una reserva DHCP a IT.
