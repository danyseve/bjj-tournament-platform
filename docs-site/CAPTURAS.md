# Capturas pendientes del Tatami

El Centro de Documentación publica hoy **esquemas** (`assets/esquema-control.svg`,
`assets/esquema-flujo.svg`), no capturas de pantalla: hasta la fecha no hay capturas reales
de la interfaz. Este fichero es la lista de lo que falta y cómo hacerlo bien.

## Como obtenerlas

1. Entra en `https://tatami1.opsforge.cc/control` con la identidad autorizada (OTP).
2. Captura la ventana del navegador a pantalla completa (sin barra de marcadores ni otras
   pestañas).
3. Guarda el PNG en `docs-site/assets/capturas/` con el nombre indicado abajo.
4. **No** incluyas datos personales innecesarios: nombres de competidores reales, correos,
   ni la barra de direcciones con parámetros. Si aparecen, tapa esa zona antes de guardar.
5. Reconstruye (`docs-site/deploy.sh`) y revisa que la guía A4 siga siendo 1 página.

## Lista

| Fichero | Estado del tatami | Que debe verse |
| --- | --- | --- |
| `control-tatami-libre.png` | `sin combate asignado` | Visor y `/control` en vacío, reloj sin arrancar |
| `control-combate-asignado.png` | `Combate asignado` | Nombres de los dos competidores, marcador a 0, reloj en la duración de la categoría |
| `control-en-curso.png` | `Combate en curso` | Reloj corriendo y algún punto anotado |
| `control-tiempo-finalizado.png` | `pendiente de resultado` | Panel de finalización visible |
| `control-finalizado.png` | `Combate finalizado` | Ganador y método en pantalla |
| `visor.png` | cualquiera | Pantalla pública `/` (solo lectura) para el proyector |

## Donde se usan

- Manual del árbitro: sección 3 (visor vs control), 5 (combate asignado), 15 (finalizar).
- Guía rápida A4: solo si cabe en la cara A4 sin perder el formato de una página.
