# 08 - Nginx como frontal interno

## Objetivo

Añadir un frontal Nginx interno para acceder a Bracket mediante una URL estable desde clientes conectados a WireGuard.

## Arquitectura


iMac conectado a VPN
        |
        v
bjj.local -> 172.30.0.100
        |
        v
bjj-nginx
        |
        v
bracket:8400
