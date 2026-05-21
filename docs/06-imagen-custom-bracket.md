# 06 - Imagen custom de Bracket para BJJ Tournament Platform

## Objetivo

Crear una imagen propia de Bracket basada en `ghcr.io/evroon/bracket:latest`, aplicando los parches necesarios para que el frontend no llame a `localhost:8400`.

## Problema detectado

El frontend compilado de Bracket contenía referencias a:

```text
http://localhost:8400/api
