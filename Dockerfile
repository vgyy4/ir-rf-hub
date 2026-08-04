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
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Home Assistant base images already provide s6-overlay init.
WORKDIR /app

RUN apk add --no-cache \
        gcc \
        musl-dev \
        libffi-dev \
        openssl-dev \
        sqlite

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/ir_rf_hub /app/ir_rf_hub
COPY --from=frontend-build /backend/ir_rf_hub/static /app/ir_rf_hub/static

RUN pip install --no-cache-dir --break-system-packages .

COPY rootfs /

RUN chmod a+x /etc/s6-overlay/s6-rc.d/ir-rf-hub/run \
    && chmod a+x /backup_pre.sh /backup_post.sh

# Ingress talks to this port from inside the Supervisor's isolated network only.
EXPOSE 8099
