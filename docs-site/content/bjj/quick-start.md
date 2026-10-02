---
title: Quick Start — Acceso a BJJ Vetusta / OpsForge
slug: quick-start
short: Quick Start — Acceso
version: v0.1
date: 2026-10-02
project: OpsForge · BJJ Vetusta / Asturkon
state: Validated
order: 0
pdf: quick-start-acceso-opsforge-v0.1.pdf
---

# Quick Start — Acceso a BJJ Vetusta / OpsForge

> **Qué resuelve esta guía:** cómo se entra a cada herramienta del torneo y en qué se diferencia el
> acceso del portal, la documentación y el cuadro (abierto a cualquier email verificado) del acceso
> de los tatamis (restringido a una allow-list). Es la referencia operativa permanente de la
> política de acceso.

| | |
|---|---|
| **Versión** | v0.1 |
| **Fecha** | 2026-10-02 |
| **Proyecto** | OpsForge · BJJ Vetusta / Asturkon |
| **Estado** | Validated — matriz verificada por read-back contra la API del proveedor |
| **Alcance** | Acceso a `bjjvetusta.`, `docs.`, `bracket.` y `tatami1..6.opsforge.cc` |

## 1. Matriz objetivo

### Portal — `bjjvetusta.opsforge.cc`

- **OTP abierto**: entra cualquier dirección de email que complete correctamente el One-Time PIN.
- **Sin alta previa**: no hay que autorizar el correo antes de entrar.
- Sesión: **24 h**.

### Documentación — `docs.opsforge.cc`

- **OTP abierto**: cualquier dirección de email que complete el One-Time PIN.
- **Sin alta previa**.
- Sesión: **24 h**.

### Bracket — `bracket.opsforge.cc`

- **OTP abierto**: cualquier dirección de email que complete el One-Time PIN.
- **Sin alta previa**.
- Sesión: **24 h**.

### Tatami 1 — `tatami1.opsforge.cc`

- **Allow-list explícita**: solo los emails autorizados.
- **OTP**: One-Time PIN por correo (la allow-list decide *quién*; el OTP, *cómo* se entra).
- **Alta previa obligatoria** mediante el procedimiento `cloudflare-bjj-access`.
- Sesión: **8 h**.

### Tatamis 2 a 6 — `tatami2..6.opsforge.cc` (cuando existan)

- **Mismo modelo restringido que Tatami 1**: allow-list explícita, OTP, alta previa mediante
  `cloudflare-bjj-access` y sesión de **8 h**.

## 2. Tabla resumen

| Hostname | Modelo | Alta previa | Sesión | Quién entra |
|---|---|---|---|---|
| `bjjvetusta.opsforge.cc` | OTP abierto | No | 24 h | Cualquier email que complete el OTP |
| `docs.opsforge.cc` | OTP abierto | No | 24 h | Cualquier email que complete el OTP |
| `bracket.opsforge.cc` | OTP abierto | No | 24 h | Cualquier email que complete el OTP |
| `tatami1.opsforge.cc` | Allow-list + OTP | Sí (`cloudflare-bjj-access`) | 8 h | Solo los emails autorizados |
| `tatami2..6.opsforge.cc` | Allow-list + OTP | Sí (`cloudflare-bjj-access`) | 8 h | Solo los emails autorizados |

La diferencia es **deliberada**: portal, documentación y cuadro sirven contenido operativo sin datos
de nadie (identificar al visitante basta); el tatami controla la mesa del combate y exige saber de
antemano *quién* puede entrar.

## 3. Flujo de acceso

**Portal / Documentación / Bracket:**

`email → OTP → acceso`

**Tatamis:**

`email autorizado → OTP → acceso`

En los cuatro casos el primer paso es el login de Cloudflare Access: se abre el hostname, Access pide
la dirección de email, envía un código de un solo uso, se introduce el código y la aplicación carga.

> **No confundir OTP abierto con acceso anónimo; Cloudflare Access sigue siendo obligatorio.**

Un visitante anónimo (sin completar el OTP) no llega nunca a la aplicación: la petición se redirige
al login de Access, también en las aplicaciones abiertas. El modelo abierto **identifica** al
visitante; no lo exime de autenticarse.

Detalle operativo: la sesión de Access es **por hostname** (no hay sesión única entre aplicaciones),
así que al pasar del portal a la documentación o al cuadro se vuelve a pedir el OTP. Es el
comportamiento actual, no un error.

## 4. Gestión de árbitros

Las **altas y bajas de árbitros y profesores** (las identidades autorizadas de los tatamis) se hacen
**exclusivamente** con el procedimiento `cloudflare-bjj-access`, que resuelve la aplicación por
hostname exacto, lee antes de escribir y verifica el resultado con read-back:

- **Alta**: `add tatami1.opsforge.cc` (el hostname del tatami que corresponda).
- **Baja**: `remove` / `revoke` sobre el mismo hostname.
- **Auditoría del modelo**: `audit`, que comprueba que los tatamis mantienen allow-list a 8 h y que
  portal, documentación y cuadro siguen abiertos a 24 h.
- **Tatami nuevo**: la app de Access se crea primero (`create-app`); publicarla (DNS, túnel, nginx)
  es una tarea aparte y posterior.

**No** se gestionan árbitros modificando DNS, Tunnel, ingress ni nginx: esas capas enrutan tráfico,
no autorizan personas, y un cambio ahí **no** da ni quita acceso. Los servicios internos (Bridge,
base de datos, `/internal/*`) no tienen hostname público y no deben tenerlo.

Las direcciones autorizadas **no se versionan ni aparecen en informes**: la herramienta enmascara
las identidades en toda su salida.

## 5. Cómo comprobar que el modelo sigue en su sitio

- **Anónimo**: abrir cualquiera de los cuatro hostnames en una ventana privada → debe aparecer el
  login de Access, nunca la aplicación.
- **OTP abierto**: con un correo **no** autorizado antes, portal, documentación y Bracket deben
  permitir **solicitar** el código.
- **Restringido**: ese mismo correo en `tatami1.opsforge.cc` debe quedar **bloqueado**.
- **Auditoría**: `audit` de `cloudflare-bjj-access` sobre las cuatro aplicaciones.

La configuración concreta (aplicaciones, policies, sesiones y sus identificadores) se registra en el
repositorio, en `docs/14-documentation-center.md` y en `docs/11-demo-externa-cloudflare.md` §22.
