# Layers a small concurrency patch on top of stock Open WebUI (see
# patch_middleware.py for what/why). Rebuild with `docker compose build --pull
# open-webui` to pick up a new upstream :main and re-apply the patch; a plain
# `docker compose build` reuses the cached base layer.
FROM ghcr.io/open-webui/open-webui:main

COPY patch_middleware.py /tmp/patch_middleware.py
RUN python3 /tmp/patch_middleware.py && rm /tmp/patch_middleware.py
