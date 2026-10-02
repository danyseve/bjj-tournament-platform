# docs-site — Centro de documentación OpsForge

Documentación operativa de BJJ Vetusta / Asturkon, publicada en `https://docs.opsforge.cc`.

- **Fuente única:** Markdown con front matter en `content/`.
- **Salidas generadas** (nunca editadas a mano): HTML estático y PDF, ambas desde la misma fuente.

## Estructura

```
docs-site/
  build.py              generador (Markdown -> HTML + PDF)
  requirements.txt      markdown, fpdf2 (fijadas)
  deploy.sh             build + validación + recarga de nginx
  content/
    index.md            portada del centro
    bjj/tatami-arbitro.md
    bjj/guia-rapida-arbitro.md
    bjj/bracket.md
    bjj/organizador.md
  assets/               CSS y recursos del sitio
```

Salida (versionada en git, servida por nginx):

```
nginx/conf.d/docs-site/          <- HTML + PDF + assets
nginx/conf.d/docs.conf           <- server_name docs.opsforge.cc
```

Se sirve desde `nginx/conf.d/` porque el contenedor `bjj-nginx` monta **solo** ese
directorio: así el despliegue es un `git pull` + recarga, sin recrear el contenedor de
producción (que sirve Bracket y Tatami).

## Construir

```sh
./deploy.sh --quiet       # build + nginx -t + nginx -s reload
NO_BUILD=1 ./deploy.sh    # solo validar y recargar (p. ej. tras un git pull)
```

Venv de build (aislado, fuera del repo):

```sh
python3 -m venv --without-pip ~/.cache/docs-build/venv
curl -sS https://bootstrap.pypa.io/get-pip.py | ~/.cache/docs-build/venv/bin/python
~/.cache/docs-build/venv/bin/pip install -r docs-site/requirements.txt
```

## Añadir o modificar un manual

1. Edita (o crea) el `.md` en `content/bjj/` con su front matter:

   ```yaml
   ---
   title: Título visible
   slug: url-corta            # -> /bjj/<slug>/
   version: v0.1
   date: 2026-10-02
   project: OpsForge · BJJ Vetusta / Asturkon
   state: Draft               # Draft | Validated | Published
   order: 5
   pdf: nombre-del-pdf.pdf    # opcional: genera PDF con ese nombre
   a4: true                   # opcional: formato de guía rápida A4
   ---
   ```

2. `./deploy.sh --quiet`
3. Commit (fuente **y** salida generada): `docs-site/` + `nginx/conf.d/docs-site/`.

## Verificar

```sh
curl -sS -H 'Host: docs.opsforge.cc' http://127.0.0.1:8080/ | head
curl -sSI -H 'Host: docs.opsforge.cc' http://127.0.0.1:8080/bjj/tatami/ | head -1
curl -sSI -H 'Host: docs.opsforge.cc' http://127.0.0.1:8080/manual-arbitro-tatami-v0.1.pdf | head -1
```

Sin la cabecera `Host` el frontal sirve otra aplicación (Bracket): **siempre** usar `Host`.

## Rollback

El sitio está versionado en git: `git revert <commit>` (o `git checkout <commit> -- nginx/conf.d/docs-site`)
y `NO_BUILD=1 ./deploy.sh`. No hay estado fuera del repositorio.

Detalle operativo completo: `docs/14-documentation-center.md`.
