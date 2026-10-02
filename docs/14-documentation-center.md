# 14. Centro de documentación OpsForge (`docs.opsforge.cc`)

Estado: **P2.6A.3 — CLOSED ✅ (2026-10-02)**. Hostname publicado y detrás de Cloudflare Access.
Documentación operativa de **BJJ Vetusta / Asturkon** con una sola fuente (Markdown) que
genera las dos salidas: **sitio HTML** y **PDF descargables**.

- Sitio: `https://docs.opsforge.cc/`
- Manual del árbitro (HTML): `https://docs.opsforge.cc/bjj/tatami/`
- Manual Bracket (estructura): `https://docs.opsforge.cc/bjj/bracket/`
- Guía rápida A4 (1 página): `https://docs.opsforge.cc/bjj/guia-rapida/`
- PDFs: `https://docs.opsforge.cc/manual-arbitro-tatami-v0.1.pdf`,
  `guia-rapida-arbitro-tatami-v0.1.pdf`, `manual-bracket-v0.1.pdf`

## Arquitectura

    navegador -> Cloudflare -> Access (OTP, allow-list) -> Tunel opsforge-oracle
              -> http://127.0.0.1:8080 (bjj-nginx) -> server_name docs.opsforge.cc
              -> root /etc/nginx/conf.d/docs-site  (ficheros estaticos)

Decisiones y por qué:

- **Hostname propio de un nivel** (`docs.opsforge.cc`): cumple la regla de OpsForge
  ("cada servicio publicable, su hostname"; `opsforge.cc` sigue siendo solo landing) y entra
  en el certificado Universal SSL (`*.opsforge.cc`).
- **Sin prefijo dentro de otro hostname**: el sitio no cuelga de `bjjvetusta.opsforge.cc` ni
  de `tatami1.opsforge.cc`, así un cambio en el portal no puede romper la documentación.
- **Ports nuevo**: ninguno. Se reutiliza el frontal en 8080 y el túnel existente.
- **El frontal no se recreó**: `bjj-nginx` solo monta `nginx/conf.d` (ro), así que la salida
  del build se sirve desde ahí. El despliegue es `build + nginx -s reload` (recarga graceful,
  **cero downtime**), sin `docker compose up` y sin tocar `bjjvetusta`/`tatami1`.

## Estructura del repo

    docs-site/                 fuente y herramientas (Markdown -> HTML + PDF)
      content/                 fuente unica en Markdown con front matter
      assets/                  CSS y esquemas SVG (assets/capturas/ reservado a capturas reales)
      build.py                 generador (site manda: HTML + PDF)
      deploy.sh                build + comprobacion + recarga de nginx
      requirements.txt         markdown, fpdf2 (fijadas)
      README.md                guia corta para quien edita
    nginx/conf.d/docs.conf     server_name dedicado del sitio
    nginx/conf.d/docs-site/    SALIDA versionada (HTML + PDF) que sirve nginx

## Build

Cadena minima, sin tooling pesado (un solo script y dos librerias de Python):

    python3 -m venv --without-pip /home/ubuntu/.cache/docs-build/venv
    curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    /home/ubuntu/.cache/docs-build/venv/bin/python /tmp/get-pip.py
    /home/ubuntu/.cache/docs-build/venv/bin/pip install -r docs-site/requirements.txt
    /home/ubuntu/.cache/docs-build/venv/bin/python docs-site/build.py

El venv vive fuera del repo (`~/.cache/docs-build/venv`) para no versionar dependencias.
El comando `build.py` imprime, por documento, la ruta HTML y el PDF con su numero de paginas:
ese numero es la verificacion (la guia A4 debe ser **1 pagina**).

Detalles que importan (aprendidos en la primera ejecucion):

- `fpdf2` rechaza etiquetas anidadas dentro de `<td>`: el generador aplana el formato inline
  de las celdas solo para el PDF (el HTML mantiene negritas y codigo).
- `multi_cell` en fpdf2 >= 2.7 deja el cursor a la derecha por defecto: el generador pasa
  `new_x="LMARGIN", new_y="NEXT"` en la cabecera del PDF.
- Los caracteres fuera de Latin-1 (`—`, `“`, `→`) no existen en las fuentes base del PDF:
  `build.py` los translitera (`pdf_safe`) y avisa en consola.
- Los esquemas SVG se publican en la version online; el PDF los omite (fpdf2 no los renderiza
  de forma fiable) y conserva la leyenda.

## Despliegue

    docs-site/deploy.sh            # build + nginx -t + recarga (idempotente)

O manualmente, si el sitio ya esta construido y solo cambian los estaticos:

    docker exec bjj-nginx nginx -t && docker exec bjj-nginx nginx -s reload

Validacion local sin depender de Access (con `Host` exacto, **nunca sin Host**: sin cabecera
el frontal sirve el server por defecto, que es el cuadro de Bracket):

    curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: docs.opsforge.cc' http://127.0.0.1:8080/bjj/tatami/

## Como actualizar los manuales

1. Edita el Markdown en `docs-site/content/bjj/` (front matter: `title`, `slug`, `version`,
   `date`, `project`, `state`, `order`, `pdf`/`a4`).
2. Sube `version` y `date` si el cambio es de contenido; `state` pasa de `Draft` a
   `Validated` cuando un árbitro lo valida y a `Published` cuando se entrega al club.
3. `docs-site/deploy.sh` y revisa que la guia A4 siga en 1 pagina.
4. Commit con la fuente **y** la salida (`nginx/conf.d/docs-site/`).

## Rollback

El contenido servido esta versionado, asi que revertir es un `git revert` del commit del
centro de documentacion (vuelve fuente + salida) y una recarga. Nada de estado oculto: no hay
base de datos, ni procesos, ni volumenes que limpiar. Si el frontal se recrease alguna vez,
`nginx/conf.d/docs-site/` sigue estando en el bind mount, asi que el sitio se sirve igual.

## Control de acceso: decisión y análisis

Se publica **protegido por Cloudflare Access** (opción B). Análisis que lo sostiene:

| Criterio | Público (A) | Protegido (B, elegido) |
| --- | --- | --- |
| Conveniencia para el árbitro | Sin fricción | Un OTP por sesión larga (7 días) |
| Exposición de procedimientos internos | Abierta: nombres de flujo, estados y métodos de victoria del club | Solo para identidades autorizadas |
| Riesgo de que un enlace filtrado active comandos de tatami | Nulo (contenido estatico) | Nulo (contenido estatico) |
| Coherencia con el resto de OpsForge | Rompe el patrón (Tatami 1 y BJJ ya van con Access) | Mantiene el patrón |
| Coste operativo | Cero | Una app de Access y su allow-list |

Aunque el contenido es estático y de bajo riesgo, publicarlo abierto contradiría el patrón de
la fase y expondría el procedimiento interno del club sin necesidad. Se elige B y se mitiga la
fricción con **sesión larga**.

Configuración aplicada (app Access independiente, nunca `Everyone`, nunca wildcard):

- App `OpsForge Documentation`, dominio `docs.opsforge.cc`, tipo self-hosted.
- **1 identidad autorizada**, allow-list explícita, `decision=allow`, **sin** `login_method`
  (nada de "cualquier correo verificado").
- `session_duration=168h` (7 días), IdP `onetimepin` (OTP por correo).
- La app se creó copiando las identidades de la app de Tatami 1 con
  `create-app-host --copy-from tatami1`: **ningún correo pasa por la línea de comandos ni
  aparece en la salida**. Para cambiar la lista, usa `access_admin.sh add/remove/check`
  (ver skill `cloudflare-bjj-access`); no edites DNS ni túnel para eso.

Observación pre-existente (no tocada): la app de `bjjvetusta.opsforge.cc` mantiene su
`login_method` (cualquier correo verificado por OTP). Es anterior a esta fase y su política
queda intacta; se documenta como pendiente de decisión del club, no como cambio de P2.6A.3.

## Seguridad

- Cero puertos inbound nuevos: solo se añadió un hostname.
- El sitio no expone `/internal/*` (404 explícito), no habla con la BD ni con el bridge, y no
  ejecuta nada en el servidor: son ficheros estáticos.
- Sin secretos en el repo: ni correos reales, ni tokens, ni OTP, ni credenciales. La
  identidad autorizada vive solo en la app de Access.
- Cabeceras en el `server_name` de docs: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, y cache corta para estáticos.

## Pendientes (mini-tareas, no bloquean el cierre)

1. **Enlace "? Manual" en `/control`** (no se ha tocado la UI del Tatami, a propósito): el
   scoreboard se sirve desde su imagen, así que añadir el enlace implica reconstruir y
   redesplegar el contenedor del tatami. Se hará como cambio atómico propio, no dentro del
   centro de documentación.
2. **Capturas reales** del visor y de `/control` (checklist en `docs-site/CAPTURAS.md`):
   hoy solo hay esquemas anotados.
3. **Manual Bracket y del Organizador**: publicados como esqueleto; falta el contenido
   detallado y el `Login exacto` de Bracket.
4. **Enlaces desde el portal BJJ** (`bjjvetusta.opsforge.cc`): se añadirán en P2.6B junto con
   los botones de Tatami 1–6.

## Versionado mostrado en cada manual

Cada página y cada PDF llevan **versión, fecha, proyecto y estado** en su cabecera, tomados
del front matter: el manual del árbitro y la guía rápida son `v0.1`, `2026-10-02`, proyecto
`OpsForge · BJJ Vetusta / Asturkon`, estado `Draft`.
