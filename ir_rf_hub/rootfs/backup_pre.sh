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
