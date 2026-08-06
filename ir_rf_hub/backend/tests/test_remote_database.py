from __future__ import annotations

from ir_rf_hub.esphome.protocol_decode import DecodedSignal, decode_nec, encode_nec
from ir_rf_hub.esphome.remote_database import lookup_bundled, search_bundled


def test_lookup_bundled_finds_real_awa_tv_entry():
    # Same real Flipper-IRDB sample used in test_protocol_decode.py
    # (TVs/AWA/AWA_MSDV3268O5D0.ir, "Power") -- proves the bundled index
    # built by scripts/build_flipper_index.py is actually reachable via a
    # decoded signal's address_bytes/command_bytes, not just present in
    # the raw file.
    decoded = DecodedSignal(
        protocol="NECext", address=0xDF00, command=0xE31C, address_bytes="00 DF 00 00", command_bytes="1C E3 00 00"
    )
    matches = lookup_bundled(decoded)
    assert any(m.brand == "AWA" and m.model == "MSDV3268O5D0" and m.button == "Power" for m in matches)
    assert all(m.source == "bundled" for m in matches)


def test_lookup_bundled_empty_for_protocols_not_indexed():
    # Only NEC/NECext are indexed today -- see remote_database.py.
    decoded = DecodedSignal(protocol="SIRC", address=1, command=1)
    assert lookup_bundled(decoded) == []


def test_lookup_bundled_empty_for_a_code_not_in_the_database():
    decoded = DecodedSignal(
        protocol="NEC", address=0xFFFF, command=0xFFFF, address_bytes="FF FF FF FF", command_bytes="FF FF FF FF"
    )
    assert lookup_bundled(decoded) == []


def test_search_bundled_finds_a_real_entry_by_brand_and_button():
    results = search_bundled("awa power")
    assert any(r.brand == "AWA" and r.model == "MSDV3268O5D0" and r.button == "Power" for r in results)


def test_search_bundled_ranks_brand_matches_above_incidental_ones():
    results = search_bundled("lg power", limit=10)
    assert results, "expected at least one match"
    assert results[0].brand == "LG"


def test_search_bundled_excludes_the_low_quality_converted_category():
    # _Converted_ entries have placeholder brand/model names (e.g. "CSV",
    # "0  1") from an auto-conversion with no real attribution -- useless
    # as a search result, see build_flipper_index.py's _EXCLUDED_CATEGORIES.
    results = search_bundled("power", limit=500)
    assert all(r.category != "_Converted_" for r in results)


def test_search_bundled_ignores_stopwords_and_empty_query():
    assert search_bundled("") == []
    assert search_bundled("turn on the") == []  # every word is a stopword


def test_search_bundled_results_are_fireable():
    # The whole point: a search result must round-trip through encode_nec
    # into a real raw timing list, and that timing list must decode back
    # to the same code -- otherwise "pick a result and save it" would
    # silently save the wrong signal.
    results = search_bundled("awa power")
    match = next(r for r in results if r.brand == "AWA")
    timings = encode_nec(match.address_bytes, match.command_bytes)
    decoded = decode_nec(timings)
    assert decoded is not None
    assert decoded.address_bytes == match.address_bytes
    assert decoded.command_bytes == match.command_bytes
