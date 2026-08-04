# Must be declared before the FIRST FROM in the file to be usable inside
# any later FROM's image reference -- Docker only extends ARG scope into
# FROM instructions for ARGs declared before the first FROM, not merely
# before the FROM that uses them. Declaring it later (as this file
# originally did) silently resolves to blank, which buildx then rejects.
ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

# --- stage 1: build the Svelte SPA -----------------------------------------
# A separate, non-arch-pinned stage: the frontend build only ever needs to
# *run* on the builder's host platform (buildx handles that automatically),
# it never runs on-device, so it doesn't need to track BUILD_FROM/arch.
FROM node:22-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Writes into ../backend/ir_rf_hub/static per vite.config.ts's outDir.
RUN npm run build


# --- stage 2: the App image --------------------------------------------------
# https://developers.home-assistant.io/docs/apps/configuration#app-dockerfile
# Since Supervisor 2026.04.0, BUILD_FROM is no longer injected by the
# builder -- the default above IS the actual base image, and build.yaml
# (which used to map this per-arch) is deprecated and no longer read.
# This is a plain Alpine base (not a python-flavored variant, which no
# longer exists as a separate published image), so Python is installed
# explicitly below.
FROM ${BUILD_FROM}

# Home Assistant base images already provide s6-overlay init.
WORKDIR /app

RUN apk add --no-cache \
        python3 \
        py3-pip \
        gcc \
        musl-dev \
        libffi-dev \
        openssl-dev \
        sqlite

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/ir_rf_hub /app/ir_rf_hub
COPY --from=frontend-build /backend/ir_rf_hub/static /app/ir_rf_hub/static

RUN pip install --no-cache-dir --break-system-packages .

# alembic.ini sits next to pyproject.toml, not inside the ir_rf_hub/
# package -- `pip install .` (packages = ["ir_rf_hub"]) never ships it, so
# it has to be placed explicitly at a fixed path the running app can find
# regardless of where pip decided to install the package itself (that's
# not /app -- see IR_RF_HUB_ALEMBIC_INI in the run script and config.py).
COPY backend/alembic.ini /app/alembic.ini

COPY rootfs /

RUN chmod a+x /etc/s6-overlay/s6-rc.d/ir-rf-hub/run \
    && chmod a+x /backup_pre.sh /backup_post.sh

LABEL \
    org.opencontainers.image.title="IR/RF Command Hub" \
    org.opencontainers.image.description="Record, name, edit, and fire IR/RF commands through ESPHome IR/RF proxy devices" \
    org.opencontainers.image.source="https://github.com/vgyy4/ir-rf-hub" \
    org.opencontainers.image.licenses="Apache License 2.0"

# Ingress talks to this port from inside the Supervisor's isolated network only.
EXPOSE 8099
