"""Fetches, parses, merges, and deduplicates the bundled remote-code
databases into the single index format remote_database.py loads. Shared
by two callers:

- scripts/build_remote_database.py -- the dev-time generator for the
  committed bundled snapshot (ir_rf_hub/data/remote_db_index.json.gz),
  which ships in the image so search/lookup work even with zero network
  access.
- main.py's runtime updater -- periodically refreshes a second copy in
  /data at runtime so the bundled snapshot doesn't go stale between App
  releases (see remote_database_updater.py). Same code path either way,
  so a source added here benefits both without extra work.

Sources today:
- Flipper-IRDB (github.com/Lucaslhm/Flipper-IRDB, CC0) -- NEC/NECext
  entries only, and specifically excludes its "_Converted_" category
  (auto-converted entries with placeholder brand/model attribution like
  "CSV"/"0  1" -- not useful for a name-based search or suggestion).
- IRDB (github.com/probonopd/irdb) -- NEC-family entries (NEC, NEC1,
  NEC2, NECx1, NECx2), which all share the identical single-shot D:8,S:8,
  F:8,~F:8 frame shape per the canonical IRP protocol definitions
  (bengtmartensson/IrpTransmogrifier) -- confirmed empirically to add
  real, non-overlapping coverage (measured ~3x the unique codes already
  in Flipper-IRDB alone). IRDB's own license requires informing the irdb
  project of any product using it and including an attribution notice --
  both handled outside this code (see DOCS.md / ARCHITECTURE.md).

  IRDB's own README suggests accessing it dynamically per-file over a CDN
  (jsDelivr) at runtime rather than bundling a static snapshot, so a
  product "benefits from updates ... automatically". Deliberately not
  done that way here: the goal that suggestion is actually protecting
  against -- shipping a copy that's frozen forever at whatever it was
  when the product was built -- is already solved by
  remote_database_updater.py's periodic re-fetch (checked on startup, on
  every App version bump, and weekly). Fetching this same tree as ~3,200
  individual jsDelivr requests instead of one `git clone` would cost
  materially more (requests, latency, failure surface) for no additional
  freshness over what the periodic refresh already provides, and
  wouldn't remove the need for a local cache anyway -- offline search
  (this project's whole point, see api/rest/remote_database.py) requires
  a copy already resident locally regardless of how it got fetched.
- UberGuidoZ/Flipper's Sub-GHz/ folder (GPL-3.0) -- RF, filtered to
  Princeton and CAME (see rf_protocol_decode.py's docstring for why only
  these two, and why rolling-code protocols like KeeLoq are excluded
  outright regardless of whether they're decodable). Sparse-cloned (only
  Sub-GHz/, not the ~2.2GB full repo) but still ~600MB even so -- mostly
  photos/diagrams bundled alongside the actual .sub files, which a git
  blob-size filter turns out not to help with once sparse-checkout
  materializes the tree. That size is genuinely too large to re-fetch on
  a schedule on typical add-on hardware, so unlike the two IR sources
  above, this one is NOT part of the runtime updater's periodic refresh
  (see remote_database_updater.py) -- it's only refreshed when a
  maintainer re-runs scripts/build_remote_database.py for a new App
  release, i.e. bundled-snapshot-only.
"""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FLIPPER_IRDB_URL = "https://github.com/Lucaslhm/Flipper-IRDB"
IRDB_URL = "https://github.com/probonopd/irdb"
FLIPPER_SUBGHZ_URL = "https://github.com/UberGuidoZ/Flipper"

_FLIPPER_SUPPORTED_PROTOCOLS = {"NEC", "NECext"}
_FLIPPER_EXCLUDED_CATEGORIES = {"_Converted_"}
_IRDB_NEC_FAMILY = {"NEC", "NEC1", "NEC2", "NECx1", "NECx2"}
_SUBGHZ_SUPPORTED_PROTOCOLS = {"Princeton", "CAME"}


@dataclass
class RawEntry:
    protocol: str  # "NEC" | "NECext" (normalized across sources)
    address_bytes: str
    command_bytes: str
    category: str
    brand: str
    model: str
    button: str
    source: str  # "flipper-irdb" | "irdb"


def _normalize_hex_bytes(raw: str) -> str:
    return " ".join(b.upper().zfill(2) for b in raw.split())


def _clean_name_part(part: str) -> str:
    return part.replace("_", " ").replace("-", " ").strip()


def _git_clone(url: str, dest: Path) -> None:
    subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True, capture_output=True)


def _git_sparse_clone(url: str, dest: Path, sparse_path: str) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", url, str(dest)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "sparse-checkout", "set", sparse_path], cwd=dest, check=True, capture_output=True)


# --- Flipper-IRDB ----------------------------------------------------------

# One entry inside a .ir file, e.g.:
#   name: Power
#   type: parsed
#   protocol: NECext
#   address: 00 DF 00 00
#   command: 1C E3 00 00
_FLIPPER_ENTRY_RE = re.compile(
    r"^name:\s*(?P<name>.+?)\s*$\n"
    r"^type:\s*parsed\s*$\n"
    r"^protocol:\s*(?P<protocol>\S+)\s*$\n"
    r"^address:\s*(?P<address>[0-9A-Fa-f ]+?)\s*$\n"
    r"^command:\s*(?P<command>[0-9A-Fa-f ]+?)\s*$",
    re.MULTILINE,
)


def _parse_flipper_ir_file(path: Path, category: str, brand: str) -> list[RawEntry]:
    text = path.read_text(encoding="utf-8", errors="replace")
    model = _clean_name_part(path.stem.removeprefix(f"{path.parent.name}_").removeprefix(f"{brand}_"))
    entries = []
    for match in _FLIPPER_ENTRY_RE.finditer(text):
        protocol = match["protocol"]
        if protocol not in _FLIPPER_SUPPORTED_PROTOCOLS:
            continue
        entries.append(
            RawEntry(
                protocol=protocol,
                address_bytes=_normalize_hex_bytes(match["address"]),
                command_bytes=_normalize_hex_bytes(match["command"]),
                category=category,
                brand=brand,
                model=model or brand,
                button=_clean_name_part(match["name"]),
                source="flipper-irdb",
            )
        )
    return entries


def fetch_flipper_irdb(work_dir: Path) -> list[RawEntry]:
    repo_dir = work_dir / "flipper-irdb"
    _git_clone(FLIPPER_IRDB_URL, repo_dir)
    entries: list[RawEntry] = []
    for category_dir in sorted(
        p
        for p in repo_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in _FLIPPER_EXCLUDED_CATEGORIES
    ):
        for brand_dir in sorted(p for p in category_dir.iterdir() if p.is_dir()):
            for ir_file in sorted(brand_dir.rglob("*.ir")):
                entries.extend(_parse_flipper_ir_file(ir_file, category_dir.name, brand_dir.name))
    logger.info("Flipper-IRDB: parsed %d entries", len(entries))
    return entries


# --- IRDB --------------------------------------------------------------------


def _parse_irdb_csv(path: Path, brand: str, category: str) -> list[RawEntry]:
    entries: list[RawEntry] = []
    # Filenames are "<device>,<subdevice>.csv" -- IRDB has no real model
    # name field at all (unlike Flipper's), so the numeric pair is the
    # closest thing to a distinguishing identifier it actually provides.
    model = f"Device {path.stem}"
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                protocol = (row.get("protocol") or "").strip()
                if protocol not in _IRDB_NEC_FAMILY:
                    continue
                try:
                    device = int(row["device"])
                    subdevice = int(row["subdevice"])
                    function = int(row["function"])
                except (KeyError, ValueError, TypeError):
                    continue
                if not (0 <= device <= 255 and 0 <= subdevice <= 255 and 0 <= function <= 255):
                    continue
                # IRDB stores only one function byte, never an
                # independently-captured complement -- so unlike Flipper's
                # data, "NEC" vs "NECext" here can only be judged from the
                # address half; the command half is always exactly the
                # complement by construction (protocol_decode.encode_nec
                # computes it when rendering timings, IRDB never recorded
                # it separately in the first place).
                is_standard_address = subdevice == (255 - device)
                entries.append(
                    RawEntry(
                        protocol="NEC" if is_standard_address else "NECext",
                        address_bytes=f"{device:02X} {subdevice:02X} 00 00",
                        command_bytes=f"{function:02X} {(~function) & 0xFF:02X} 00 00",
                        category=category,
                        brand=brand,
                        model=model,
                        button=_clean_name_part(row.get("functionname") or ""),
                        source="irdb",
                    )
                )
    except (OSError, csv.Error):
        logger.debug("Skipping unreadable IRDB file %s", path, exc_info=True)
    return entries


def fetch_irdb(work_dir: Path) -> list[RawEntry]:
    repo_dir = work_dir / "irdb"
    _git_clone(IRDB_URL, repo_dir)
    codes_dir = repo_dir / "codes"
    entries: list[RawEntry] = []
    for brand_dir in sorted(p for p in codes_dir.iterdir() if p.is_dir()):
        for category_dir in sorted(p for p in brand_dir.iterdir() if p.is_dir()):
            for csv_file in sorted(category_dir.glob("*.csv")):
                entries.extend(_parse_irdb_csv(csv_file, brand_dir.name, category_dir.name))
    logger.info("IRDB: parsed %d entries", len(entries))
    return entries


# --- UberGuidoZ/Flipper Sub-GHz -----------------------------------------------

_SUBGHZ_FIELD_RE = {
    "filetype": re.compile(r"^Filetype:\s*(.+)$", re.MULTILINE),
    "protocol": re.compile(r"^Protocol:\s*(\S+)$", re.MULTILINE),
    "bit": re.compile(r"^Bit:\s*(\d+)$", re.MULTILINE),
    "key": re.compile(r"^Key:\s*([0-9A-Fa-f ]+?)\s*$", re.MULTILINE),
    "te": re.compile(r"^TE:\s*(\d+)$", re.MULTILINE),
}


def _parse_subghz_file(path: Path, category: str, brand: str) -> RawEntry | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    filetype_match = _SUBGHZ_FIELD_RE["filetype"].search(text)
    if filetype_match is None or "Key File" not in filetype_match[1]:
        return None  # "RAW File" -- a raw capture, not a parsed protocol+key

    protocol_match = _SUBGHZ_FIELD_RE["protocol"].search(text)
    bit_match = _SUBGHZ_FIELD_RE["bit"].search(text)
    key_match = _SUBGHZ_FIELD_RE["key"].search(text)
    if protocol_match is None or bit_match is None or key_match is None:
        return None
    protocol = protocol_match[1]
    if protocol not in _SUBGHZ_SUPPORTED_PROTOCOLS:
        return None

    # RF .sub files are one code each (unlike a multi-button .ir/.csv
    # file), so there's no separate function/button field to read --
    # bit_count/te get folded into the "button" label since they're what
    # actually distinguishes otherwise-identical-looking captures for the
    # same device (e.g. a 12-bit vs 24-bit variant).
    te_match = _SUBGHZ_FIELD_RE["te"].search(text)
    te_us = int(te_match[1]) if te_match else None
    model = _clean_name_part(path.stem)
    button = f"{bit_match[1]}-bit" + (f" @ {te_us}us" if te_us else "")

    return RawEntry(
        protocol=protocol,
        address_bytes=_normalize_hex_bytes(key_match[1]),  # repurposed: the raw Key: hex for RF
        command_bytes=bit_match[1],  # repurposed: the bit count for RF
        category=category,
        brand=brand,
        model=model,
        button=button,
        source="flipper-subghz",
    )


def fetch_flipper_subghz(work_dir: Path) -> list[RawEntry]:
    """Only ever called by scripts/build_remote_database.py's CLI, never
    by the runtime updater -- see this module's docstring for why (~600MB
    sparse-clone, too large to re-fetch on a schedule)."""
    repo_dir = work_dir / "flipper-subghz"
    _git_sparse_clone(FLIPPER_SUBGHZ_URL, repo_dir, "Sub-GHz")
    subghz_root = repo_dir / "Sub-GHz"
    entries: list[RawEntry] = []
    for sub_file in sorted(subghz_root.rglob("*.sub")):
        rel_parts = sub_file.relative_to(subghz_root).parts
        category = rel_parts[0]
        # Files sit at varying depth (Category/File.sub, Category/Brand/
        # File.sub, Category/Sub/Brand/File.sub, ...) -- the immediate
        # parent directory is the closest thing to "brand" at any depth;
        # falls back to the category itself for files with no brand
        # subfolder at all.
        brand = rel_parts[-2] if len(rel_parts) > 1 else category
        entry = _parse_subghz_file(sub_file, category, brand)
        if entry is not None:
            entries.append(entry)
    logger.info("UberGuidoZ/Flipper Sub-GHz: parsed %d entries", len(entries))
    return entries


# --- merge + dedup ----------------------------------------------------------


def merge_and_dedupe(entries: list[RawEntry]) -> dict[str, list[dict]]:
    """Groups by "<protocol>|<address>|<command>" (the physical code) same
    as a single-source index always did, but now also deduplicates
    *within* a group: multiple sources independently cataloging the same
    real remote (same brand+model+button, case/whitespace-insensitive)
    collapse into one listed match carrying a combined `sources` list,
    rather than showing an identical name twice just because two
    databases happen to agree on it.
    """
    grouped: dict[str, dict[tuple[str, str, str], dict]] = {}
    for entry in entries:
        key = f"{entry.protocol}|{entry.address_bytes}|{entry.command_bytes}"
        dedupe_key = (entry.brand.strip().lower(), entry.model.strip().lower(), entry.button.strip().lower())
        bucket = grouped.setdefault(key, {})
        existing = bucket.get(dedupe_key)
        if existing is None:
            bucket[dedupe_key] = {
                "category": entry.category,
                "brand": entry.brand,
                "model": entry.model,
                "button": entry.button,
                "sources": [entry.source],
            }
        elif entry.source not in existing["sources"]:
            existing["sources"].append(entry.source)

    return {key: list(bucket.values()) for key, bucket in grouped.items()}


def build_index(work_dir: Path, *, include_subghz: bool = True) -> dict[str, list[dict]]:
    """Clones every source into work_dir, parses, and returns the final
    merged+deduped index. Network access + at least several seconds
    required (minutes, if include_subghz -- see fetch_flipper_subghz's
    docstring) -- callers decide when that's acceptable.

    include_subghz defaults to True (the dev CLI script's own use, for
    building the full bundled snapshot) but the runtime updater always
    passes False -- its periodic refresh only covers the two small IR
    sources, never the ~600MB Sub-GHz source.
    """
    entries: list[RawEntry] = []
    entries.extend(fetch_flipper_irdb(work_dir))
    entries.extend(fetch_irdb(work_dir))
    if include_subghz:
        entries.extend(fetch_flipper_subghz(work_dir))
    index = merge_and_dedupe(entries)
    logger.info("Merged index: %d unique codes from %d raw entries", len(index), len(entries))
    return index
