---
title: Manual de Bracket (estructura)
slug: bracket
short: Manual Bracket (estructura)
version: v0.1
date: 2026-10-02
project: OpsForge · BJJ Vetusta / Asturkon
state: Draft
order: 3
pdf: manual-bracket-v0.1.pdf
---

# Manual de Bracket

> **Estado: ESTRUCTURA.** Este documento es el esqueleto de trabajo del manual. Solo se
> documentará lo verificado contra la aplicación en producción; lo que aún no se ha comprobado
> aparece marcado como *Pendiente*. No se han inventado credenciales, usuarios ni flujos.

**Login exacto pendiente de cierre operativo.**

| | |
|---|---|
| **Versión** | v0.1 (estructura) |
| **Fecha** | 2026-10-02 |
| **Proyecto** | OpsForge · BJJ Vetusta / Asturkon |
| **Estado** | Draft |
| **Alcance** | Bracket de BJJ Vetusta (`bracket.opsforge.cc`) |

## 0. Qué es Bracket y qué no

- **Bracket** es donde vive el torneo: club, torneo, categorías, competidores, equipos, cuadro,
  combates y clasificaciones.
- **No** es la mesa del tatami: el marcador y el reloj se operan en el Tatami
  (`docs.opsforge.cc/bjj/tatami/`).
- Hoy el resultado del tatami **no** llega a Bracket automáticamente.

## 1. Login

- Pantalla de acceso de la aplicación (`login`). Cuenta de usuario de la aplicación.
- Recuperación de contraseña (`password_reset`) y alta de cuenta (`create_account`).
- **Pendiente:** *Login exacto pendiente de cierre operativo.*
- **Pendiente:** definir quién tiene cuenta, con qué rol y en qué club. **No documentar
  credenciales en este manual ni en ningún fichero del repositorio.**

## 2. Crear torneo

- Sección de **torneos**: listado y ficha del torneo (`tournaments`, `tournaments/[id]`).
- Datos de cabecera: nombre, fechas, club, estado del torneo.
- **Pendiente:** capturas y pasos exactos del alta de un torneo real.

## 3. Categorías

- División de la competición (cinturones, edades, pesos). En la aplicación se apoya en **stages**.
- **Pendiente:** cómo se nombran y se ordenan las categorías en Vetusta, y su relación con las
  clases de peso.

## 4. Competidores

- Alta y gestión de **jugadores/competidores** (`players`).
- Datos mínimos, club de origen, categoría asignada.
- **Pendiente:** plantilla de alta y criterios de corrección de errores.

## 5. Equipos

- Alta y gestión de **equipos** (`teams`) y su relación con los competidores (equipos de uno o
  varios competidores según modalidad).
- **Pendiente:** reglas de composición usadas en Vetusta/Asturkon.

## 6. Stages

- Estructura de la competición (`stages`, `stage_items`, `stage_item_inputs`) y **rondas**
  (`rounds`).
- **Pendiente:** qué plantilla de stages se usa por categoría.

## 7. Brackets

- Construcción del cuadro a partir de los stages y sus inscritos.
- **Pendiente:** pasos de generación, resiembra y correcciones manuales.

## 8. Matches

- Los **combates** (`matches`) y su estado: pendiente, asignado, en curso, finalizado.
- **Pendiente:** cómo se ve un combate desde Bracket y qué campos son oficiales.

## 9. Asignación de Tatamis

- Los **tatamis** son "courts" en la aplicación (`courts`): cada tatami físico es una cancha.
- Un combate se asigna a un tatami; a partir de ahí el Tatami muestra los dos luchadores y el
  marcador (ver Manual Tatami / Árbitro).
- Hoy la asignación se realiza por el flujo operativo del torneo (el portal con botones está
  pendiente).
- **Pendiente:** pantalla de asignación y criterios de reparto entre Tatamis 1-6.

## 10. Resultados

- Resultado del combate y su reflejo en el cuadro y en las **clasificaciones** (`rankings`).
- **Muy importante:** hoy el resultado del tatami **no se escribe** en Bracket
  (`BRACKET_RESULT_WRITE_ENABLED=false`). El cierre definitivo del resultado en Bracket es
  **manual** y está **pendiente de definición operativa**.
- **Pendiente:** procedimiento oficial de cierre de resultados y de publicación de
  clasificaciones.

## 11. Troubleshooting

| Síntoma | Comprobación | Nota |
|---|---|---|
| No puedo entrar | ¿Correo/cuenta autorizada? ¿Cloudflare Access pide código? | *(pendiente de detallar)* |
| El cuadro no refleja un resultado | El resultado del tatami no se escribe automáticamente | *(pendiente de procedimiento)* |
| Un competidor está mal inscrito | Revisar ficha del competidor y su categoría | *(pendiente)* |
| Un combate no aparece en el tatami | Revisar asignación del combate al tatami | *(pendiente)* |

## Pendiente de despliegue

1. **Write-back** del resultado del tatami a Bracket (`BRACKET_RESULT_WRITE_ENABLED=false`).
2. **Portal operativo** con botones a Tatami 1-6, Bracket, Manuales y GitHub.
3. **Login exacto y roles** documentados.
4. **Capturas y pasos verificados** de cada sección de este manual.

*Manual operativo del árbitro pendiente; antes de entregar `/control` a usuarios finales se
publicará documentación online y PDF.*
