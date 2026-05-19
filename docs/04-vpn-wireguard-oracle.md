
# 04 - VPN WireGuard en Oracle Cloud A1

## Objetivo

Levantar un servidor WireGuard en Docker para acceder de forma segura al laboratorio BJJ Tournament Platform desplegado en Oracle Cloud A1.

La VPN será la primera capa de acceso al entorno. Bracket, Bridge API y los scoreboards no deberían exponerse públicamente a Internet.

## Datos de red

- IP pública Oracle: `143.47.47.86`
- IP privada Oracle: `10.0.0.67`
- Puerto WireGuard: `51820/udp`
- Red VPN: `10.8.0.0/24`

## Importante

No usar `10.0.0.0` como red VPN porque puede entrar en conflicto con la VCN privada de Oracle Cloud.

Usar:

```text
10.8.0.0/24


## Checklist de validación

- [x] Regla de entrada en Oracle creada para `UDP 51820`
- [x] Regla incorrecta `TCP 51820` identificada como causa del fallo
- [x] Contenedor WireGuard arrancado correctamente
- [x] Puerto `51820/udp` escuchando en Ubuntu/Docker
- [x] Cliente macOS conectado con peer1
- [x] Ping correcto a `10.8.0.1`
- [x] Full tunnel validado
- [x] Salida a Internet desde cliente VPN usando IP pública Oracle `143.47.47.86`
- [ ] Acceso desde VPN a Bracket `http://10.0.0.67:8400`
- [ ] Acceso desde VPN a Bridge API `http://10.0.0.67:8500/health`
- [ ] Acceso desde VPN a Scoreboard Tatami 1 `http://10.0.0.67:3001`



## Validación real desde cliente macOS

Prueba de salida pública:

```bash
curl ifconfig.me
143.47.47.86```

ping 10.8.0.1
64 bytes from 10.8.0.1: icmp_seq=0 ttl=64 time=12.746 ms
64 bytes from 10.8.0.1: icmp_seq=1 ttl=64 time=12.767 ms
64 bytes from 10.8.0.1: icmp_seq=2 ttl=64 time=12.609 ms

#NOTAS Incidencias
#Incidencia detectada
#Inicialmente se creó la regla de entrada en Oracle Cloud como TCP 51820.
#WireGuard requiere UDP 51820.
#Tras corregir la regla a UDP, la conectividad quedó validada.
