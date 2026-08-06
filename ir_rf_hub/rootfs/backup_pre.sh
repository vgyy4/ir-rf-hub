#!/command/with-contenv bashio
# shellcheck shell=bash
#
# Runs before Supervisor snapshots this App's /data volume. The command
# database is opened in WAL mode, so a naive file copy mid-write can capture
# an inconsistent snapshot; force a full checkpoint so backup.db reflects a
# clean, restorable state.

DB_PATH="/data/ir_rf_hub.db"

if [ -f "${DB_PATH}" ]; then
    bashio::log.info "Checkpointing database before backup..."
    sqlite3 "${DB_PATH}" "PRAGMA wal_checkpoint(FULL);"
fi

# The runtime remote-database cache (esphome/remote_database_updater.py)
# is a re-fetchable copy of public upstream data, not something a backup
# needs to preserve -- bloating every backup with several hundred KB of
# data that would just get re-downloaded on next startup anyway (see
# remote_database_updater.py's own on-restart/on-version-change refresh
# check) isn't worth it. Moved out of /data for the brief window Supervisor
# is actually snapshotting it, then moved back by backup_post.sh -- a
# restore that catches it mid-move just means the App re-fetches it once
# on next start, same as any install that's simply never fetched yet.
CACHE_DIR="/data/remote_db_cache"
CACHE_HOLD_DIR="/tmp/remote_db_cache_backup_hold"

if [ -d "${CACHE_DIR}" ]; then
    bashio::log.info "Excluding remote database cache from backup..."
    rm -rf "${CACHE_HOLD_DIR}"
    mv "${CACHE_DIR}" "${CACHE_HOLD_DIR}"
fi
