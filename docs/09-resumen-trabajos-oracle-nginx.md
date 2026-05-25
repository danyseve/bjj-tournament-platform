# 09 - Resumen de trabajos realizados: Oracle Cloud A1 + WireGuard + Bracket + Nginx

## Objetivo

Documentar el estado alcanzado en la maqueta Oracle Cloud A1 para BJJ Tournament Platform.

El objetivo de esta fase fue dejar una base funcional formada por:

- WireGuard como acceso VPN.
- PostgreSQL como base de datos de Bracket.
- Bracket como motor de torneos.
- Imagen custom de Bracket con parche frontend.
- Nginx como frontal interno.
- Red Docker fija para estabilizar accesos desde clientes VPN.

---

## Arquitectura actual

```text
iMac conectado a WireGuard
        |
        v
bjj.local -> 172.30.0.100
        |
        v
bjj-nginx
        |
        v
bracket:8400
        |
        v
bracket-postgres:5432
