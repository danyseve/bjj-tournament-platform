# 11 — Publicación segura de la demo externa (Cloudflare Tunnel + Access)

Estado: **PREPARADO, NO PUBLICADO** (2026-10-02). No existe todavía URL externa.
Bloqueantes en §15. Nada de este documento está aplicado en producción.

## 1. Objetivo

Hacer accesible desde Internet la demo del Tatami 1 (Bracket + scoreboard) a un
grupo reducido de profesores, mediante Cloudflare Tunnel + política de acceso por
email, **sin abrir puertos inbound nuevos** en Robledo ni exponer servicios
internos (Bridge API, PostgreSQL, Docker).

Restricciones vigentes: `BRACKET_RESULT_WRITE_ENABLED=false` (sin escritura de
resultados), Tatamis 2–6 sin habilitar, WireGuard y PostgreSQL intactos.

## 2. Arquitectura prevista

```
navegador (profesor)
   │  HTTPS
   ▼
Cloudflare edge  ──►  Access / allow-list por email (OTP)
   │
   │  túnel saliente (cloudflared, 443/TCP saliente, sin inbound)
   ▼
robledo01 (Robledo)
   └── cloudflared ──► http://127.0.0.1:8080
                          │
                       bjj-nginx (único gateway)
                          ├── /            ──► bracket:8400      (UI + API pública)
                          ├── /tatami/1/   ──► scoreboard-tatami-1:3000 (viewer)
                          └── /socket.io/  ──► scoreboard-tatami-1:3000 (Socket.IO)

NO expuesto: bridge-api:8500 · PostgreSQL:5432 · Docker API · SSHs adicionales
```

`cloudflared` sólo establece conexiones salientes: no requiere ningún puerto
entrante nuevo (`new inbound ports opened = 0`, §12).

## 3. Inventario de exposición actual (medido 2026-10-02)

Publicado por Docker en el host:

| Contenedor | Puertos | Alcance |
|---|---|---|
| `bjj-nginx` | 0.0.0.0:8080→80 | frontal interno |
| `bracket` | 0.0.0.0:8400→8400 | API/UI Bracket |
| `wireguard` | 0.0.0.0:51820/udp | VPN |
| `bjj-bridge-api` | 8500/tcp | **solo `expose`** (sin publicar) |
| `bracket-postgres` | 5432/tcp | **solo `expose`** (sin publicar) |
| `scoreboard-tatami-1` | 3000/tcp | **solo `expose`** (sin publicar) |

Escaneo externo real (check-host.net, 2–5 nodos independientes, TCP):

| Puerto | Resultado externo |
|---|---|
| 22 (SSH) | **abierto** (preexistente, gestión) |
| 8080 | filtrado / timeout |
| 8400 | filtrado / timeout |
| 8500 | filtrado / timeout (5/5) |
| 3000 | filtrado / timeout |
| 5432 | filtrado / timeout |

Conclusión: la OCI Security List + firewall del host bloquean todo salvo SSH.
Por tanto **la demo no depende de abrir nada**: el túnel es estrictamente saliente.

Clasificación:

- PUBLICABLE: UI del Bracket, rutas públicas del Bracket, viewer del Tatami 1.
- NO PUBLICABLE: `bridge-api`, PostgreSQL, Docker API/socket, SSH adicional,
  rutas `/internal/*` del scoreboard, puertos internos directos.

## 4. Estrategia de túnel

**A. Tunnel gestionado** (recomendado a medio plazo): requiere cuenta Cloudflare
con una zona/dominio propio; da hostname estable (`demo-bjj.<dominio>`) y Access
completo. **No disponible hoy**: no hay credenciales, ni `~/.cloudflared`, ni
dominio configurado (`BRACKET_PUBLIC_BASE_URL` está vacío). No se inventa ninguno.

**B. Quick Tunnel con allow-list de email** (fallback para demo temporal):
verificado en el binario instalado (`cloudflared 2026.9.3`, arm64) que existe el
flag:

```
--allowed-mail value   Email addresses or wildcard domains allowed to access a
                       protected Quick Tunnel. May be repeated or comma-separated.
```

No requiere cuenta ni dominio: da un hostname aleatorio `*.trycloudflare.com`,
protegido por OTP al email con navegador interactivo. Limitaciones oficiales
(developers.cloudflare.com, página de TryCloudflare): sin garantía de uptime,
~200 peticiones en vuelo, sin Server-Sent Events, el hostname **cambia al
reiniciar** el proceso y la sesión de email exige un navegador real (no scripts).
Apta para una demo, **no** para publicación estable.

Decisión propuesta: **B para la primera demo**, A cuando exista dominio.

## 5. Política de acceso

Requisitos del diseño (deny by default):

- sin acceso anónimo: toda petición exige autenticación por email;
- allow-list explícita de correos de profesores (los correos concretos se pasan
  en el host o en la consola de Cloudflare; **nunca** al repositorio);
- factor: OTP por email (Access con IdP de un solo uso);
- sesión limitada en el tiempo (Access permite fijar duración; en Quick Tunnel la
  sesión la impone Cloudflare);
- sin comodines de dominio (`@dominio.com`) salvo decisión expresa;
- revocación = quitar el correo de la allow-list (efecto inmediato en el siguiente
  intento de autenticación).

## 6. Origin

`http://127.0.0.1:8080` — el nginx existente, que ya es el frontal interno
(doc 08). Nunca apuntar el túnel a `bridge-api:8500`, `scoreboard:3000` ni
`bracket:8400` directamente: nginx debe seguir siendo el único gateway.

## 7. Rutas necesarias y cambio mínimo de nginx

Necesario para el profesor: `/` (UI Bracket), rutas públicas del Bracket ya
existentes, `/tatami/1/` (viewer) y `/tatami/1/control/` (operador).

Hallazgo de diseño (verificado en el código): el scoreboard sirve su UI con
**rutas absolutas desde la raíz** (`/css/`, `/js/`, `/images/`, `/manifest.json`,
`/socket.io/socket.io.js`) y su cliente hace `io()` sin `path` (conexión al
`/socket.io/` de la raíz). El Bracket, en cambio, es una SPA con catch-all
(`backend/app.py:169-182`): cualquier ruta desconocida devuelve `index.html` con
HTTP 200. Montar el scoreboard sólo bajo `/tatami/1/` rompería silenciosamente su
UI (los assets los serviría el Bracket con 200 y contenido equivocado).

Diseño mínimo resultante (aditivo; los prefijos que se desvían al scoreboard no
son assets reales del Bracket, que usa `/assets/`, `/api/`, `/favicon.svg`):

```
location = /tatami/1            -> 301 /tatami/1/
location /tatami/1/             -> proxy_pass http://scoreboard-tatami-1:3000/;   (retira el prefijo)
location /socket.io/            -> proxy_pass http://scoreboard-tatami-1:3000/socket.io/;  (Upgrade + timeouts)
location /css/                  -> scoreboard
location /js/                   -> scoreboard   (incluye /js/main.js de la UI integrada)
location /images/               -> scoreboard
location = /manifest.json       -> scoreboard
location /api/                  -> bracket      (sin cambios)
location /                      -> bracket      (sin cambios)
```

Validación realizada **sin tocar producción**: el diseño se probó con
`nginx -t -c /tmp/nginx.conf` copiado al contenedor `bjj-nginx` (sin reload ni
restart): `syntax is ok` / `test is successful`, con resolución correcta de los
upstreams `bracket` y `scoreboard-tatami-1`. El nginx productivo no se modificó
(mismo contenedor `4d8d8390fcab`, mismo `StartedAt`).

Plantilla versionada, **no activa** (fuera del bind mount `nginx/conf.d/`):
`deploy/demo-tatami1/nginx-tatami1-demo.conf.example`.

## 8. Viewer vs operador

- VIEWER: `/tatami/1/` (marcador), `/` (bracket).
- OPERADOR: `/tatami/1/control` y `/tatami/1/control2` (`scoreboard-adapter/integrated.js:18`).

Separar viewer y operador por hostname exigiría la estrategia A (dos hostnames).
Hallazgo de seguridad importante: el canal Socket.IO del scoreboard **no
autentica los comandos de control** — `integrated.js:84-99` reemite
`bjj:score` / `bjj:restart` / `bjj:start` y aplica `tatami:update` sin comprobar
token (`requireInternalToken` protege sólo las rutas HTTP `/internal/*`). Por
tanto, para cualquier usuario autenticado en la demo, la allow-list de email es la
**única** frontera real: ocultar `/control` en nginx reduce ruido pero no es una
barrera (los comandos pueden emitirse desde la consola del navegador). Se
recomienda no exponer `/control` en la primera demo y registrar la autorización
por rol como deuda de producto antes de una cohorte mayor.

## 9. Socket.IO / WebSocket

Verificado contra el scoreboard real (sin exponer nada):

- handshake `GET /socket.io/?EIO=4&transport=polling` → **HTTP 200** con
  `sid` y `upgrades:["websocket"]`;
- el cliente (`main.js:1` → `const socket = io();`, socket.io 4.8.1) usa el path
  raíz `/socket.io/`, por lo que nginx debe proxearlo con
  `Upgrade`/`Connection` y `proxy_read_timeout` largo (diseño en §7);
- Cloudflare Tunnel transporta WebSocket de forma nativa; el límite práctico es
  el timeout de la conexión, no el protocolo.

Un HTTP 200 del HTML **no** acredita el socket: la prueba definitiva es el
handshake + reconexión + actualización de marcador desde fuera (§15, pendiente).

## 10. Write gate

`BRACKET_RESULT_WRITE_ENABLED=false` se mantiene. Comprobado de nuevo durante
esta fase: `POST /tatamis/1/result` → **HTTP 503 `result_write_disabled`**, y cero
peticiones `POST /api/token` / `PUT` hacia el Bracket. La publicación de la demo
no cambia este flag: la demo es de **sólo lectura** sobre resultados.

## 11. Secretos y despliegue del proceso

- Quick Tunnel: no usa token ni credenciales.
- Tunnel gestionado: token/`credentials.json` en `/etc/cloudflared`, `0600 root`,
  fuera del repositorio y fuera de `docker-compose.yml`.
- Preferencia: **servicio systemd en el host** (no contenedor). Motivo: el origen
  es `127.0.0.1:8080`, así que un contenedor exigiría `network_mode: host` (más
  privilegio, se salta el aislamiento de la red `bjj-net`) sin aportar nada; el
  servicio systemd permite arranque controlado, logs en journald y revocación
  inmediata. Plantilla sin secretos:
  `deploy/demo-tatami1/cloudflared-demo-quick.service.example`.
- Los correos de los profesores no se versionan: van en el propio unit
  (`--allowed-mail`, vía `EnvironmentFile` con permisos restrictivos) o en la
  consola de Cloudflare.
- `sudo -n` en Robledo está disponible para instalar/gestionar el servicio.

## 12. Firewall

`new inbound ports opened = 0`. No se tocó ninguna Security List de OCI, ni
ufw/nftables, ni puertos del host: el túnel es saliente (443/TCP hacia Cloudflare).

## 13. Rollback / desactivar la demo (inmediato)

Nada de esto afecta a la aplicación ni a la base de datos.

```bash
# 1) Cortar la publicación (URL muerta al instante)
sudo systemctl stop cloudflared-demo        # servicio host (quick o gestionado)
sudo systemctl disable cloudflared-demo     # opcional: impedir arranque al reboot
# equivalente puntual si se lanzó a mano:
#   pkill -f 'cloudflared tunnel --url'

# 2) Tunnel gestionado: además, borrar DNS/route y el túnel
cloudflared tunnel route dns demo-bjj delete   # (nombre real del hostname)
cloudflared tunnel delete bjj-demo-robledo

# 3) Access (sólo estrategia A): deshabilitar la aplicación Access o borrar la
#    allow-list en la consola → 403 inmediato para todos.

# 4) Verificación del cierre
curl -sS -o /dev/null -w '%{http_code}\n' https://<hostname-de-la-demo>/   # 000/530
```

Verificación adicional tras cerrar: `docker ps` sin cambios y
`new inbound ports opened = 0`.

## 14. Pruebas locales ya realizadas (sin exponer nada)

- nginx `127.0.0.1:8080` responde 200 en `/` y `/api/ping`;
- UI del scoreboard (`/` y `/control`) 200, HTML sin ninguna URL absoluta ni
  referencias a `localhost`/`172.30.x.x` (todo relativo a la raíz);
- handshake Socket.IO 200 (origen);
- `nginx -t` del diseño de rutas: OK (§7);
- logs de nginx/bracket/bridge/scoreboard: 0 errores, 0 secretos, 0 tokens;
- gate de escritura: 503 (§10).

## 15. Bloqueantes y decisiones pendientes

1. **Sin cuenta/dominio Cloudflare en Robledo** → la estrategia A (hostname
   estable + Access completo) no se puede ejecutar. Alternativa B operativa.
2. **Falta autorización de correos**: la demo autenticada necesita al menos un
   correo real en la allow-list (el del propio titular para la prueba controlada).
   No se usa ni se inventa ningún correo sin autorización expresa, y la prueba
   externa exige además leer el OTP en el buzón.
3. **Cambio de nginx no aplicado** (diseñado y validado): sin él la demo no
   muestra el Tatami 1. Requiere autorización por ser un cambio en el frontal
   productivo (backup + `nginx -t` + recarga controlada).
4. ~~**Match 1 residual `ready`**~~ **RESUELTO en P2.6A.1 (2026-10-02)**: la
   operación administrativa `cancel_assignment` libera un combate asignado por
   error que nunca ha arrancado (rama `command.operation === 'cancel_assignment'`
   en `scoreboard-adapter/state.js`), y `/control` gana la acción separada
   "Cancelar asignación" en dos pasos. El match 1 quedó liberado por ese flujo
   soportado —estado `null`, persistido y conservado tras reinicio— sin tocar
   `state.json` a mano ni forzar la máquina de estados; ver §17. El 409 de
   `assign()` ya no bloquea la reasignación.

## 16. Resultado de P2.6A

Preparación completa y verificada; publicación **no** realizada por los
bloqueantes 1–3. Ver informe de fase.

## 17. P2.6A.1 — operación administrativa `cancel_assignment` (CLOSED ✅, 2026-10-02)

Desbloquea el match residual antes de publicar la demo. No toca Bracket, no
escribe resultados, no modifica PostgreSQL, no abre puertos ni rutas HTTP
nuevas: el comando viaja **sólo por Socket.IO** con la misma credencial de
control que el resto de operaciones administrativas.

Contrato (detalle en `scoreboard-adapter/README.md` y en sus tests):

- Sólo se acepta sobre un match activo `ready`, con el reloj completo
  (`remaining_seconds === duration_seconds`), el marcador a cero y sin ganador
  ni método.
- Rechaza `running`, `paused`, `awaiting_result` y `finished` (`not_ready`) y
  cualquier `ready` con puntos, ventajas o penalizaciones (`not_clean`): no es
  un atajo para cerrar un combate ni un bypass de `finish`.
- Efecto: deja el tatami vacío (estado activo, `session_id`, reloj e historial
  de comandos), persiste `state: null` y difunde `tatami:state` con `null`.
- Idempotencia: repetir el mismo `command_id` responde el mismo ack sin volver a
  mutar (memoria en proceso, acotada a ese `command_id`; tras un reinicio no hay
  nada que cancelar y el reintento se rechaza con `wrong_session`).
- UI: "Cancelar asignación" en `/control`, visible y habilitada sólo con un
  combate `ready` intacto, con confirmación en dos pasos y separada de
  "Liberar Tatami" (que sigue siendo la liberación posterior a `finish`).

Evidencia del cierre sobre producción (2026-10-02):

- Imagen release `danyseve1/bjj-scoreboard@sha256:6fe745874fffd1a83ede55c3716307e6829f2d51d6e385f8a4b5e3836b4c1c71`
  (tag `375e26c-r1`), Compose pinneado por digest y recreado **sólo**
  `scoreboard-tatami-1`; Bracket, Bridge, PostgreSQL, nginx y WireGuard con los
  mismos IDs y sin reinicios.
- Match 1: `ready/rev1` → `cancel_assignment` → ack `{ok:true, revision:2}`,
  difusión `["tatami:state", null]`, estado `null`; tras reiniciar el contenedor
  sigue `null`. Candidatos del torneo 1: 12, con match 1 de nuevo en la lista.
- Cero escrituras a Bracket: `POST /tatamis/1/result` → 503
  `result_write_disabled`; métricas del Bracket sin `POST`/`PUT`/`api/token`;
  DB sin cambios (2/25/10/16/9/15, Alembic `c1ab44651e79`).
