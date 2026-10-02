---
title: Manual del Tatami / Árbitro
slug: tatami
short: Manual Tatami / Árbitro
version: v0.1
date: 2026-10-02
project: OpsForge · BJJ Vetusta / Asturkon
state: Draft
order: 1
pdf: manual-arbitro-tatami-v0.1.pdf
---

# Manual del Tatami / Árbitro

Este manual describe **solo** lo que el sistema hace hoy en producción. Lo que todavía no
está desplegado se marca de forma explícita en la sección *Pendiente de despliegue*.

| | |
|---|---|
| **Versión** | v0.1 |
| **Fecha** | 2026-10-02 |
| **Proyecto** | OpsForge · BJJ Vetusta / Asturkon |
| **Estado** | Draft (pendiente de validación por un árbitro y de revisión operativa) |
| **Alcance** | Tatami 1 (`tatami1.opsforge.cc`) |

## 1. Qué es el Tatami

El **Tatami** es la aplicación que se usa durante el combate: cronometra, lleva el marcador y
guarda el resultado del combate en curso. En el sistema convive con otras dos piezas:

- **Bracket**: el cuadro del torneo y los combates (quién contra quién). Aquí no se opera.
- **Tatami (esta aplicación)**: la mesa de cada tatami. Un tatami es una unidad independiente:
  el Tatami 1 no ve ni afecta a los demás.

El resultado que se produce aquí es **el resultado oficial del combate mientras está en
memoria**. Hoy **no se escribe automáticamente en Bracket** (ver *Pendiente de despliegue*).

Estado del sistema en esta versión: `BRACKET_RESULT_WRITE_ENABLED=false`, es decir, el
resultado **no se publica** en el cuadro del torneo. Es intencionado.

## 2. Acceso con Cloudflare OTP

El acceso está protegido por **Cloudflare Access** con **código de un solo uso (OTP)** enviado
al correo autorizado.

1. Abre en el navegador la dirección del tatami (por ejemplo `https://tatami1.opsforge.cc`).
2. Cloudflare pedirá tu correo. Escribe **el correo autorizado** y pulsa *Send me a code*.
3. Recibirás un código de un solo uso. Escríbelo en la pantalla de verificación.
4. Si el código es correcto, entrarás en la aplicación.

Notas de operación:

- La sesión dura varias horas (8 h en el Tatami 1). Caducado el plazo, se vuelve a pedir el código.
- **No se puede entrar con un correo que no esté en la lista autorizada.** Si un compañero no
  entra, no es un fallo de la aplicación: su correo no está autorizado.
- El código caduca en pocos minutos y es de un solo uso. Si expira, se pide otro.
- **No compartas el enlace fuera del equipo autorizado**: aunque no tengan código, la dirección
  no debe circular.

## 3. Viewer `/` y control `/control` (diferencia)

La misma aplicación tiene dos pantallas con permisos distintos:

| | Viewer `/` | Control `/control` |
|---|---|---|
| Para qué sirve | Pantalla pública del tatami (proyector, TV, público) | Mesa del árbitro |
| Qué muestra | Marcador, nombres, categoría, reloj | Todo lo del viewer **más** los botones de operación |
| ¿Se puede operar? | **No**. Es solo lectura | **Sí**. Es la única pantalla que opera |
| Identificación en pantalla | El indicador de la esquina dice `Read-only` | El indicador de la esquina dice `Control` |

Regla práctica: **el proyector siempre en `/`; el árbitro siempre en `/control`.** Abrir
`/control` en la pantalla del público da a cualquiera la posibilidad de modificar el combate.

Arriba a la izquierda, en ambos casos, hay una etiqueta de estado de la forma
`Integrated · <estado> · Control|Read-only` que indica la pantalla y el estado del combate.

![Esquema de zonas de la pantalla de control](/assets/esquema-control.svg)

*Esquema de zonas (no es una captura). Los números remiten a las secciones siguientes
de este manual.*

## 4. Estado "Tatami libre"

Cuando el tatami no tiene ningún combate asignado, el viewer muestra:

> **Tatami 1 libre — sin combate asignado**

En ese estado el marcador está a cero (`0` y `—`), el reloj muestra `--:--` y **los controles
del árbitro están bloqueados**: no se puede puntuar porque no hay combate.

## 5. Combate asignado

Un combate **no se elige desde esta pantalla**. La asignación llega desde el flujo operativo del
torneo (hoy la realiza el operador; el portal para hacerlo desde el móvil está pendiente, ver
*Pendiente de despliegue*).

Cuando el combate queda asignado, la pantalla pasa al estado **`ready`** y aparecen:

- los dos competidores,
- la categoría y la duración,
- el marcador a **0 – 0**,
- el reloj en la **duración de la categoría, sin arrancar**.

`ready` significa *preparado pero el reloj no ha empezado*. El árbitro decide cuándo empieza.

![Diagrama de estados del Tatami](/assets/esquema-flujo.svg)

*Estados del Tatami y acciones que los provocan. El estado vive en el servidor: la
pantalla solo lo refleja.*

## 6. Identificación de los dos competidores

Los dos competidores aparecen como **luchador A** (izquierda) y **luchador B** (derecha). Los
nombres los fija la asignación del torneo: el árbitro **no los escribe ni los corrige aquí**
(los campos de nombre no se editan en esta versión; ver *Qué NO hacer*).

## 7. Marcador

Cada luchador tiene su propio bloque con:

- **Puntos totales** del luchador (suma de sus puntos).
- Tres filas de puntuación (4, 3 y 2 puntos), cada una con su contador.
- **Ventaja** y **Penalización**, cada una con su contador.
- El **reloj** es común a los dos luchadores.

## 8. Puntos: 4, 3 y 2

Cada fila tiene dos botones: **+** suma y **−** resta (la resta existe para **deshacer un
error**).

| Puntos | Acción (según la interfaz actual) |
|---|---|
| **4** | Montada, Toma de espalda |
| **3** | Pase de guardia |
| **2** | Derribo, Raspada, Rodilla al pecho |

El **+** de una fila suma la cantidad de esa fila (4, 3 o 2). El **−** de la misma fila resta esa
misma cantidad. El contador de la fila y el total del luchador se actualizan a la vez.

Ejemplo: dos derribos = `+2` dos veces en la fila **2**; el total del luchador sube a 4.

## 9. Ventajas

La **Ventaja** se lleva con **+ / −** (una unidad por pulsación). Se usa para el desempate: a
igualdad de puntos, gana quien tiene **más ventajas**. Si te equivocas, el **−** quita la ventaja
que acabas de dar.

## 10. Penalizaciones

La **Penalización** se lleva igual, con **+ / −** (una unidad por pulsación).

La aplicación **solo cuenta**: no aplica automáticamente ninguna regla de descalificación ni
convierte penalizaciones en puntos. Si el combate termina por acumulación de penalizaciones, el
árbitro lo cierra a mano eligiendo el método **Descalificación** (ver sección 14).

## 11. Reloj

El reloj es **una cuenta atrás** que empieza en la **duración de la categoría** (por ejemplo
6:00) y baja hacia cero. Es el mismo para los dos luchadores.

Controles del reloj:

| Botón | Qué hace |
|---|---|
| **Iniciar / Pausa** | Arranca o detiene la cuenta. Es un interruptor: el mismo botón para y arranca. |
| **Reiniciar** (icono de apagado) | Devuelve el reloj a la duración inicial y lo deja parado. |
| **+ / −** junto al reloj | Ajusta el tiempo en **un minuto** por pulsación (para corregir la duración). |

Cuando el tiempo llega a cero, el sistema **no elige ganador**: pasa a
**"Tiempo finalizado — pendiente de resultado"** y el resultado lo decide el árbitro.

## 12. Iniciar / pausar

El combate **solo acepta puntuación y cambios de reloj mientras está en marcha o en pausa**
(estados `ready`, `running`, `paused`). Con el tiempo agotado o el combate ya finalizado, los
botones quedan **bloqueados**: no se puede puntuar un combate cerrado.

## 13. Resultado / ganador

El ganador **nunca lo calcula la aplicación**, ni siquiera cuando se acaba el tiempo. Lo decide
el árbitro y lo declara en la pantalla de finalización (sección 15), eligiendo uno de los dos
competidores:

- `A · <nombre del luchador A>`
- `B · <nombre del luchador B>`

## 14. Método

Junto al ganador se declara **cómo** se ganó. La lista de métodos disponibles es:

| Valor | Etiqueta en pantalla |
|---|---|
| `points` | Puntos |
| `submission` | Sumisión |
| `decision` | Decisión |
| `disqualification` | Descalificación |
| `walkover` | Walkover |
| `referee_stoppage` | Parada del árbitro |
| `other` | Otro |

## 15. Finalizar combate

Finalizar es una acción **en dos pasos** para que no se cierre un combate por un toque
accidental:

1. Elige en los desplegables el **Ganador…** y el **Método…**.
2. Pulsa **Finalizar…**. Aparecerá la pregunta *¿Finalizar como ganador X por Y?*
3. Pulsa **Confirmar finalización** (o **Cancelar** si te has equivocado).

Tras confirmar, el estado pasa a **`finished`**, la pantalla muestra
`Finalizado · Ganador: <nombre> · <método>` y **el combate queda cerrado**: ya no acepta
puntuación ni cambios de reloj. El resultado queda en la pantalla hasta que se libera el tatami.

## 16. `cancel_assignment` (Cancelar asignación)

Se usa **solo para corregir una asignación equivocada**. El botón **Cancelar asignación** aparece
únicamente cuando el combate está **recién asignado y sin tocar** (sin puntuación, sin ventajas,
sin penalizaciones, sin reloj arrancado y sin resultado).

1. Pulsa **Cancelar asignación**.
2. Confirma con **Confirmar cancelación** (o **Cancelar** para dejarlo como estaba).

El combate vuelve a quedar **sin asignar** (vuelve a la lista de candidatos) y la pantalla vuelve
a *Tatami libre*. **No sirve para terminar un combate**: para eso está Finalizar (sección 15).

## 17. `clear_match` (Liberar Tatami)

Es la acción de **cierre, después de finalizar**. Sirve para dejar el tatami limpio para el
siguiente combate.

1. Con el combate en `finished`, pulsa **Liberar Tatami**.
2. Confirma con **Confirmar liberación** (aviso: *"¿Liberar el Tatami? El resultado en memoria se
   perderá."*).

Tras liberar, la pantalla vuelve a **Tatami libre**. Aviso importante: el resultado **se pierde
de la memoria del sistema**; dado que en esta versión el resultado **no se escribe en Bracket**
(WRITE deshabilitado), **anota el resultado en el acta del tatami antes de liberar**.

## 18. Qué hacer tras un reinicio o un refresco

El estado **vive en el servidor**, no en el navegador. Por eso:

- **Si recargas la página** (`F5`): vuelves a ver el mismo combate, con el mismo marcador. El
  reloj sigue donde estaba: el navegador solo dibuja lo que el servidor dice.
- **Si se cierra el navegador o se va la pantalla**: al volver a entrar, el combate continúa igual.
- **Si un error obliga a recargar**, una vez recargado comprueba el indicador de estado y el
  marcador (ver sección 20).

Recomendación: **no recargues con el combate en marcha** salvo necesidad. Si lo haces, revisa el
reloj y el marcador antes de continuar.

## 19. Qué NO hacer

- **No operes desde dos pantallas a la vez.** Si dos páginas de control lanzan órdenes a la vez,
  el servidor acepta solo la primera y **descarta la otra sin avisar**. Un control, una mesa.
- **No abras `/control` en la pantalla del público**: cualquiera podría tocar el marcador.
- **No compartas el enlace de `/control`** ni el correo autorizado.
- **No cierres el combate a mano sin Finalizar**: usa el cuadro de finalización. No hay botón de
  borrar para eso.
- **No uses "Cancelar asignación" para terminar un combate** (solo desasigna combates sin tocar).
- **No puntúes después de finalizar**: el sistema bloquea los botones, pero tampoco lo intentes.
- **No escribas los nombres de los luchadores a mano**: los fija la asignación; lo que escribas
  se pierde y no se publica.
- **No esperes que el resultado aparezca en Bracket**: en esta versión **no se escribe** (WRITE
  deshabilitado). Anota el acta.
- **No toques la infraestructura** (servicios, contenedores, configuración) durante el torneo.

## 20. Problemas frecuentes

| Síntoma | Causa habitual | Qué hacer |
|---|---|---|
| No veo los botones, todo está en gris | Estás en `/` (solo lectura) | Usa `/control` |
| El indicador dice `Read-only` y necesito operar | Pantalla equivocada | Abre `/control` |
| No me deja añadir puntos | El combate no está en marcha/pausa (`ready`, `running`, `paused`) o ya está finalizado | Comprueba el estado y el reloj; si terminó, hay que finalizar |
| Pulso y no pasa nada | La orden ha llegado tarde: otro dispositivo ya había cambiado el combate, así que el servidor la ha descartado (**no avisa**) | Recarga la página y vuelve a intentarlo |
| El reloj no avanza | Está en pausa (`Pausa`/`Iniciar`) o el combate no ha empezado | Pulsa Iniciar |
| Pone "Tiempo finalizado — pendiente de resultado" | Se ha agotado el tiempo y falta declarar el resultado | Elige Ganador y Método y finaliza (sección 15) |
| El marcador no cambia en la pantalla del público | La pantalla del público no se ha enterado (se ha caído la conexión) | Recarga `/` en la pantalla del público |
| Reloj a `--:--` y todo vacío | Tatami libre (no hay combate asignado) | Espera la asignación del operador |
| Me pide un código al entrar | La sesión de Access ha caducado | Vuelve a entrar con el correo autorizado |
| "No se ha podido acceder" / error de Cloudflare | Correo no autorizado | No es un fallo de la aplicación: contacta con el equipo organizador |
| La pantalla se queda congelada | Se ha perdido la conexión con el servidor | Comprueba la red y recarga |

## 21. Contacto y soporte

- **Soporte operativo durante el torneo**: equipo de organización de BJJ Vetusta / Asturkon
  (canal interno del club).
- **Incidencias técnicas**: repositorio del proyecto en GitHub
  (`danyseve/bjj-tournament-platform`), indicando el tatami, la hora y el estado que mostraba la
  pantalla.
- **Documentación**: `https://docs.opsforge.cc/bjj/tatami/`

## Pendiente de despliegue (NO disponible hoy)

Se marca de forma explícita para que nadie lo busque en la aplicación:

1. **Escritura automática del resultado en Bracket (write-back).** Hoy el resultado se queda en
   la memoria del tatami: `BRACKET_RESULT_WRITE_ENABLED=false`. El resultado **no** se publica en
   el cuadro del torneo ni en Bracket.
2. **Roles internos de árbitro.** No hay usuarios ni permisos dentro de la aplicación: quien
   entra en `/control` puede operar. La única barrera es Cloudflare Access.
3. **Asignación desde el móvil (portal del operador).** La asignación del combate la hace hoy el
   operador por el flujo técnico; el portal con botones (Tatami 1-6, Bracket, Manuales, GitHub)
   está pendiente.
4. **Enlace "Manual" dentro de `/control`.** Pendiente de una mini-tarea de interfaz.
5. **Publicación automática de resultados, clasificaciones y actas.**

*Manual operativo del árbitro pendiente; antes de entregar `/control` a usuarios finales se
publicará documentación online y PDF.*
