#!/command/with-contenv bashio
# shellcheck shell=bash
#
# Other half of backup_pre.sh's remote-database-cache exclusion: puts it
# back in /data now that Supervisor is done snapshotting.

CACHE_DIR="/data/remote_db_cache"
CACHE_HOLD_DIR="/tmp/remote_db_cache_backup_hold"

if [ -d "${CACHE_HOLD_DIR}" ]; then
    bashio::log.info "Restoring remote database cache after backup..."
    rm -rf "${CACHE_DIR}"
    mv "${CACHE_HOLD_DIR}" "${CACHE_DIR}"
fi
