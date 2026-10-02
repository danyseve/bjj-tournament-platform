# 14. Centro de documentación OpsForge (`docs.opsforge.cc`)

Estado: **P2.6A.3 — CLOSED ✅ (2026-10-02)**. Hostname publicado y detrás de Cloudflare Access.
Documentación operativa de **BJJ Vetusta / Asturkon** con una sola fuente (Markdown) que
genera las dos salidas: **sitio HTML** y **PDF descargables**.

- Sitio: `https://docs.opsforge.cc/`
- Manual del árbitro (HTML): `https://docs.opsforge.cc/bjj/tatami/`
- Manual Bracket (estructura): `https://docs.opsforge.cc/bjj/bracket/`
- Guía rápida A4 (1 página): `https://docs.opsforge.cc/bjj/guia-rapida/`
- Quick Start — Acceso a BJJ Vetusta / OpsForge (política de acceso):
  `https://docs.opsforge.cc/bjj/quick-start/`
- PDFs: `https://docs.opsforge.cc/manual-arbitro-tatami-v0.1.pdf`,
  `guia-rapida-arbitro-tatami-v0.1.pdf`, `manual-bracket-v0.1.pdf`,
  `quick-start-acceso-opsforge-v0.1.pdf`

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
- Los PDF fijan su fecha de creacion a la del front matter (`set_creation_date`): sin eso,
  fpdf2 sella la hora del build, cada rebuild ensucia el repositorio y la salida deja de ser
  reproducible. Con la fecha fija, dos builds seguidos dan el **mismo md5**.

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
| Conveniencia para el árbitro | Sin fricción | Un OTP por sesión (24 h) |
| Exposición de procedimientos internos | Abierta: nombres de flujo, estados y métodos de victoria del club | Solo para identidades autorizadas |
| Riesgo de que un enlace filtrado active comandos de tatami | Nulo (contenido estatico) | Nulo (contenido estatico) |
| Coherencia con el resto de OpsForge | Rompe el patrón (Tatami 1 y BJJ ya van con Access) | Mantiene el patrón |
| Coste operativo | Cero | Una app de Access y su allow-list |

Aunque el contenido es estático y de bajo riesgo, publicarlo abierto contradiría el patrón de
la fase y expondría el procedimiento interno del club sin necesidad. Se elige B y se mitiga la
fricción con **sesión larga**.

Configuración aplicada (app Access independiente, nunca `Everyone`, nunca wildcard):

- App `OpsForge Documentation`, dominio `docs.opsforge.cc`, tipo self-hosted.
- Modelo de acceso **normalizado en P2.6B.1**: `login_method = One-Time PIN` (cualquier email que
  complete OTP), `decision=allow`, 0 identidades explícitas. La configuración inicial (allow-list de
  1 identidad, sin `login_method`) queda documentada en `docs/11` §21–§22.
- `session_duration=24h` (desde P2.6B.1; antes 168 h), IdP `onetimepin` (OTP por correo).
- La app se creó copiando las identidades de la app de Tatami 1 con
  `create-app-host --copy-from tatami1`: **ningún correo pasa por la línea de comandos ni
  aparece en la salida**. Para cambiar la lista, usa `access_admin.sh add/remove/check`
  (ver skill `cloudflare-bjj-access`); no edites DNS ni túnel para eso.

Observación (actualizada en P2.6B.1): las apps de `bjjvetusta`, `docs` y `bracket` comparten el
modelo `login_method = One-Time PIN` (cualquier correo verificado por OTP, 24 h) por decisión del
club; los tatamis mantienen allow-list explícita a 8 h. Ver `docs/11` §22.

**Referencia operativa publicada**: la matriz de acceso, el flujo (`email -> OTP -> acceso`
frente a `email autorizado -> OTP -> acceso`) y la gestión de árbitros están documentados en
el propio centro, en `Quick Start — Acceso a BJJ Vetusta / OpsForge` (`/bjj/quick-start/`, PDF
`/quick-start-acceso-opsforge-v0.1.pdf`). Las altas y bajas de árbitros se hacen **solo** con
el procedimiento `cloudflare-bjj-access`, nunca tocando DNS, túnel, ingress ni nginx.

## Seguridad

- Cero puertos inbound nuevos: solo se añadió un hostname.
- El sitio no expone `/internal/*` (404 explícito), no habla con la BD ni con el bridge, y no
  ejecuta nada en el servidor: son ficheros estáticos.
- Sin secretos en el repo: ni correos reales, ni tokens, ni OTP, ni credenciales. La
  identidad autorizada vive solo en la app de Access.
- Cabeceras en el `server_name` de docs: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, y cache corta para estáticos.

## Diagnostico rapido: `Error 525`/`522` en un hostname ya publicado

Sintoma tipico: el navegador con sesion de Access devuelve `Cloudflare Error 525 — SSL handshake failed`
mientras los sondeos anonimos dan 302 (Access responde en el edge antes de enrutar, y tapa el fallo).

Orden de comprobacion:

1. **Origen**: en el host donde corre `cloudflared`,
   `curl -sS -o /dev/null -w '%{http_code}' -H 'Host: <host>' http://127.0.0.1:8080/<ruta>` debe dar
   **200**. El puerto publicado vive en el host de cloudflared, no en el CT de gestion.
2. **CNAME**: leer el `content` **exacto** por API (no `dig`: un registro proxied oculta el target) y
   compararlo caracter a caracter con `<TUNNEL_UUID>.cfargotunnel.com`. Un target `...cargotunnel.com`
   (sin la `f`) es un dominio de terceros (AWS) y produce 525.
3. **Ingress del túnel**: `docs.opsforge.cc -> http://127.0.0.1:8080` (HTTP local, nunca `https://` ni el
   hostname publico), antes del catch-all, `warp-routing` intacto.
4. **Edge**: `curl -sS -D - -o /dev/null https://docs.opsforge.cc/` -> 302 +
   `www-authenticate: Cloudflare-Access`.

Un target mal escrito **no** se arregla cambiando el SSL mode, abriendo 443 ni instalando certificados:
el túnel cifra la pata cloudflared<->Cloudflare y el origen sigue siendo HTTP local. La prueba final
(carga real con sesion) la hace una persona con navegador.

Incidente de origen: `docs/11-demo-externa-cloudflare.md` §23 (2026-10-02, resuelto).

## Pendientes (mini-tareas, no bloquean el cierre)

1. **Enlace "? Manual" en `/control`** (no se ha tocado la UI del Tatami, a propósito): el
   scoreboard se sirve desde su imagen, así que añadir el enlace implica reconstruir y
   redesplegar el contenedor del tatami. Se hará como cambio atómico propio, no dentro del
   centro de documentación.
2. **Capturas reales** del visor y de `/control` (checklist en `docs-site/CAPTURAS.md`):
   hoy solo hay esquemas anotados.
3. **Manual Bracket y del Organizador**: publicados como esqueleto; falta el contenido
   detallado y el `Login exacto` de Bracket.
4. **Enlaces desde el portal BJJ** (`bjjvetusta.opsforge.cc`): **HECHO en P2.6B** — el portal
   enlaza a cada manual y a su PDF (botón `MANUAL`), y a la portada del centro. Ver
   `docs/11-demo-externa-cloudflare.md` §21.

## Relación con el portal BJJ (P2.6B, 2026-10-02)

El portal operativo vive en `bjjvetusta.opsforge.cc` (`nginx/conf.d/portal/`, estático) y es
la puerta de entrada del equipo durante el torneo:

- `Tatami 1` → `ABRIR` a `https://tatami1.opsforge.cc` y `MANUAL` a `/bjj/tatami/` de este
  centro (el PDF del manual se descarga desde la portada y desde `/bjj/tatami/`).
- `Bracket` → `ABRIR` a `https://bracket.opsforge.cc` (aplicación en su propio hostname desde
  P2.6B) y `MANUAL` a `/bjj/bracket/`.
- `Tatami 2–6` aparecen como **PRÓXIMAMENTE** y sin botones activos.
- `Repositorio` → GitHub del proyecto; más un enlace a la portada de este centro.

El portal no consume ninguna API interna: su estado es estático (`portal/status.json`). Por
tanto este centro de documentación sigue siendo **estático y desacoplado** de las apps.

## Versionado mostrado en cada manual

Cada página y cada PDF llevan **versión, fecha, proyecto y estado** en su cabecera, tomados
del front matter: el manual del árbitro y la guía rápida son `v0.1`, `2026-10-02`, proyecto
`OpsForge · BJJ Vetusta / Asturkon`, estado `Draft`. El **Quick Start de acceso** es el único
`Validated`: su matriz se verificó por read-back contra la API del proveedor, así que no
documenta una intención sino el estado real de las cuatro aplicaciones.
