#!/usr/bin/env python3
"""Regenerates ir_rf_hub/data/remote_db_index.json.gz, the bundled
offline snapshot of the merged/deduped remote-code database (see
esphome/remote_database_build.py for the actual fetch/parse/merge logic,
shared with the App's own runtime updater).

Not run by the App itself -- only by a maintainer occasionally, to pick
up upstream additions and refresh the committed bundled snapshot that
ships in the image (the App also refreshes its own separate runtime copy
in /data periodically -- see remote_database_updater.py -- but the
bundled one is what a fresh install has before its first successful
network fetch, so it's still worth updating by hand now and then too).

Usage: python scripts/build_remote_database.py
"""

from __future__ import annotations

import gzip
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ir_rf_hub.esphome.remote_database_build import build_index  # noqa: E402


def main() -> None:
    out_path = Path(__file__).resolve().parent.parent / "ir_rf_hub" / "data" / "remote_db_index.json.gz"
    with tempfile.TemporaryDirectory() as tmp:
        index = build_index(Path(tmp))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, separators=(",", ":"), sort_keys=True).encode("utf-8")
    with gzip.open(out_path, "wb") as f:
        f.write(payload)
    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.0f} KiB gzipped, {len(index)} keys)", file=sys.stderr)


if __name__ == "__main__":
    main()
