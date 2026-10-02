---
title: Guía rápida — Árbitro Tatami
slug: guia-rapida
short: Guía rápida (A4)
version: v0.1
date: 2026-10-02
project: OpsForge · BJJ Vetusta / Asturkon
state: Draft
order: 2
a4: true
pdf: guia-rapida-arbitro-tatami-v0.1.pdf
---

# Guía rápida — Árbitro Tatami

**Tatami 1 · v0.1 · 2026-10-02 · Draft** — Imprimir y plastificar. Manual completo: `docs.opsforge.cc/bjj/tatami/`

## 1. Entrar

1. Abre `https://tatami1.opsforge.cc/control` (mesa del árbitro).
2. Cloudflare pide tu correo autorizado, pulsa *Send me a code*.
3. Escribe el código recibido.

La pantalla del público va en `/` (solo lectura). **Nunca en la del público `/control`.**

## 2. Reconocer el estado

| En pantalla | Significa |
|---|---|
| `Tatami 1 libre — sin combate asignado` | No hay combate. Esperar asignación del operador. |
| Dos nombres, categoría, reloj con tiempo y `0 - 0` | Combate asignado, sin arrancar (`ready`). |
| Reloj corriendo | Combate en marcha (`running`). |
| Reloj parado con tiempo restante | En pausa (`paused`). |
| `Tiempo finalizado — pendiente de resultado` | Falta declarar el resultado. |
| `Finalizado · Ganador: X · Método` | Combate cerrado. Liberar tatami. |

El indicador de arriba a la izquierda dice `Control` o `Read-only`.

## 3. Puntos, ventajas y penalizaciones

| Acción | Cómo |
|---|---|
| **4 puntos** (Montada, Toma de espalda) | Fila **4**: pulsar **+** |
| **3 puntos** (Pase de guardia) | Fila **3**: pulsar **+** |
| **2 puntos** (Derribo, Raspada, Rodilla al pecho) | Fila **2**: pulsar **+** |
| Deshacer un punto | Pulsar **−** en la misma fila |
| **Ventaja** | **+ / −** en Ventaja |
| **Penalización** | **+ / −** en Penalización |

La aplicación solo cuenta: **no** aplica reglas de descalificación automáticamente.
Solo se puede puntuar con el combate `ready`, `running` o `paused`.

## 4. Reloj

| Botón | Acción |
|---|---|
| **Iniciar / Pausa** | Arranca o para la cuenta atrás |
| **Reiniciar** (icono apagado) | Vuelve a la duración inicial, parado |
| **+ / −** | Ajusta **un minuto** |

## 5. Terminar

**Finalizar (dos pasos):**

1. Elegir **Ganador…** y **Método…** (Puntos, Sumisión, Decisión, Descalificación, Walkover,
   Parada del árbitro, Otro).
2. **Finalizar…** → **Confirmar finalización**.

**Después, liberar:** **Liberar Tatami** → **Confirmar liberación**.
**Antes de liberar, anota el resultado en el acta**: el resultado se pierde de memoria y **no se
escribe en Bracket**.

## 6. Cancelar una asignación equivocada

Solo si el combate está **recién asignado y sin tocar**:
**Cancelar asignación** → **Confirmar cancelación**. El combate vuelve a candidatos.

## 7. Si algo va mal

| Problema | Qué hacer |
|---|---|
| Un botón no hace nada | Otro dispositivo cambió el combate: **recarga y repite** (el sistema no avisa) |
| No puedo puntuar | El combate no está en marcha/pausa o ya está finalizado |
| Reloj a `--:--` | Tatami libre: falta asignación |
| Pide código al entrar | Sesión de Access caducada: vuelve a entrar |
| Pantalla congelada | Recarga la página; el estado se recupera del servidor |
| No veo los botones | Estás en `/` en vez de `/control` |

**Nunca:** operar desde dos pantallas a la vez · usar Cancelar para cerrar un combate ·
reiniciar servicios durante el torneo.
