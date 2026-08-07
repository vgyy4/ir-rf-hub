"""Matches a decoded signal (see protocol_decode.py) against the bundled
remote-code database to suggest a real remote's brand/model/button name
during recording -- a naming aid only, never authoritative: the same
address+command combination legitimately appears on more than one
physical remote (cheap universal-compatible chipsets reuse codes across
brands), so a match is a suggestion to accept or ignore, not a fact.

Two copies of the index can exist, checked in this order:
- A runtime copy at <data_dir>/remote_db_cache/, kept current by
  remote_database_updater.py's periodic background refresh.
- The bundled copy at ir_rf_hub/data/remote_db_index.json.gz, built by
  scripts/build_remote_database.py from Flipper-IRDB and IRDB (see that
  module's docstring for sources/licensing) and shipped in the App's
  image -- the fallback for a fresh install before its first successful
  update, or any install that never gets network access at all. Either
  way, looking it up needs no network access itself.
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ir_rf_hub.config import settings
from ir_rf_hub.esphome.protocol_decode import DecodedSignal
from ir_rf_hub.esphome.rf_protocol_decode import DecodedRfSignal

logger = logging.getLogger(__name__)

_BUNDLED_INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "remote_db_index.json.gz"
RUNTIME_CACHE_FILENAME = "remote_db_index.json.gz"
_MAX_MATCHES = 8

# Every key in the index is "<protocol>|<a>|<b>" -- these decide which
# protocol family a key belongs to, for both the IR/RF search filter and
# (for RF) telling entries apart from IR ones sharing the same dict.
_IR_PROTOCOLS = {"NEC", "NECext"}
_RF_PROTOCOLS = {"Princeton", "CAME"}


def runtime_cache_dir() -> Path:
    return settings.data_dir / "remote_db_cache"


@dataclass
class RemoteMatch:
    source: str  # always "bundled" today -- see remote_database_build.py for what feeds the index
    category: str
    brand: str
    model: str
    button: str


@lru_cache(maxsize=1)
def _load_index() -> dict[str, list[dict]]:
    for path in (runtime_cache_dir() / RUNTIME_CACHE_FILENAME, _BUNDLED_INDEX_PATH):
        if path.exists():
            with gzip.open(path) as f:
                return json.load(f)
    # Shouldn't happen in a real build (the bundled copy is a committed
    # asset), but a from-source checkout that skipped
    # scripts/build_remote_database.py shouldn't crash recording over a
    # purely best-effort naming aid.
    logger.warning("No remote database index found (checked runtime cache and bundled copy) -- disabled")
    return {}


def invalidate_cache() -> None:
    """Called by remote_database_updater.py right after it writes a fresh
    runtime copy, so an already-running process picks the update up
    immediately rather than only after its next restart."""
    _load_index.cache_clear()
    _search_corpus.cache_clear()


def _matches_for_key(key: str) -> list[RemoteMatch]:
    entries = _load_index().get(key, [])
    return [
        RemoteMatch(source="bundled", category=e["category"], brand=e["brand"], model=e["model"], button=e["button"])
        for e in entries[:_MAX_MATCHES]
    ]


def lookup_bundled(decoded: DecodedSignal) -> list[RemoteMatch]:
    """Only NEC/NECext are indexed today -- whatever protocol_decode.py
    can decode into Flipper-format address/command bytes (see its
    docstring). Other recognized IR protocols (e.g. Sony SIRC) still get
    shown as decoded info, just without a name suggestion yet."""
    if decoded.protocol not in _IR_PROTOCOLS or not decoded.address_bytes:
        return []
    return _matches_for_key(f"{decoded.protocol}|{decoded.address_bytes}|{decoded.command_bytes}")


def lookup_bundled_rf(decoded: DecodedRfSignal) -> list[RemoteMatch]:
    """RF equivalent of lookup_bundled -- only Princeton/CAME are indexed
    today (see rf_protocol_decode.py's docstring)."""
    if decoded.protocol not in _RF_PROTOCOLS:
        return []
    return _matches_for_key(f"{decoded.protocol}|{decoded.key_hex}|{decoded.bit_count}")


@dataclass
class SearchResult:
    """Unlike RemoteMatch (signal -> name), this is the reverse direction:
    text -> a specific fireable code. For IR (protocol in _IR_PROTOCOLS),
    address_bytes/command_bytes are exactly what protocol_decode.
    encode_nec() needs; for RF (protocol in _RF_PROTOCOLS), the same two
    fields hold the Key: hex and bit count rf_protocol_decode.
    encode_princeton()/encode_came() need -- the API layer picks the
    right encoder by checking `protocol`, see api/rest/remote_database.py.
    """

    protocol: str
    address_bytes: str
    command_bytes: str
    category: str
    brand: str
    model: str
    button: str


_MAX_SEARCH_RESULTS = 30
# Stripped from queries before matching -- someone searching types natural
# language ("turn on samsung tv"), but real button labels are terse and
# abbreviated (Flipper's own files use things like "Vol_up", "Pwr"), so
# these words would only ever dilute the match, never help it.
_STOPWORDS = frozenset(
    {"turn", "on", "off", "the", "a", "an", "please", "to", "my", "for", "set", "switch", "toggle"}
)


# Per-field weights for scoring a match -- brand and button (which
# function) are the strongest signals of what someone actually means by a
# query like "samsung tv power"; model number and category matter, but a
# stray substring hit there shouldn't outrank a real brand match.
_FIELD_WEIGHTS = {"brand": 3, "button": 2, "category": 2, "model": 1}


@lru_cache(maxsize=1)
def _search_corpus() -> list[tuple[dict[str, str], SearchResult]]:
    """Built once (the index itself is already cached by _load_index) and
    kept in memory for the process lifetime -- a plain per-field scan over
    it is fast enough for interactive search at this size (~20k deduped
    entries across both bundled sources -- see remote_database_build.py --
    measured at a few tens of ms, see search_bundled's docstring) without
    needing a real inverted-index text search engine.
    """
    corpus: list[tuple[dict[str, str], SearchResult]] = []
    for key, entries in _load_index().items():
        protocol, address_bytes, command_bytes = key.split("|")
        for e in entries:
            result = SearchResult(
                protocol=protocol,
                address_bytes=address_bytes,
                command_bytes=command_bytes,
                category=e["category"],
                brand=e["brand"],
                model=e["model"],
                button=e["button"],
            )
            fields = {
                "brand": e["brand"].lower(),
                "model": e["model"].lower(),
                "button": e["button"].lower(),
                "category": e["category"].lower(),
            }
            corpus.append((fields, result))
    return corpus


def search_bundled(query: str, *, signal_type: str = "ir", limit: int = _MAX_SEARCH_RESULTS) -> list[SearchResult]:
    """Ranked by a weighted sum of which fields each (non-stopword) query
    term appears in (see _FIELD_WEIGHTS) -- not an all-terms-must-match
    filter, since real button labels are terse/abbreviated ("Vol_up",
    "Pwr") and a natural-language query like "turn on samsung tv power"
    would otherwise fail to match a real "Samsung ... Pwr" entry just
    because "power" isn't literally present. Weighting brand highest
    matters in practice: without it, an incidental "tv"+"power" match on
    some unrelated brand can outrank the actual brand-matching entries the
    query was clearly about.

    signal_type ("ir" | "rf") filters to that protocol family only -- an
    RF search returning an IR-only code (or vice versa) would be
    unfireable through whichever transmitter the user actually picked
    beforehand, so it's not just unhelpful, it's actively misleading.
    """
    protocols = _IR_PROTOCOLS if signal_type == "ir" else _RF_PROTOCOLS
    terms = [t for t in query.lower().split() if t and t not in _STOPWORDS]
    if not terms:
        return []
    scored: list[tuple[int, SearchResult]] = []
    for fields, result in _search_corpus():
        if result.protocol not in protocols:
            continue
        score = sum(weight for field, weight in _FIELD_WEIGHTS.items() for term in terms if term in fields[field])
        if score > 0:
            scored.append((score, result))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [result for _, result in scored[:limit]]
