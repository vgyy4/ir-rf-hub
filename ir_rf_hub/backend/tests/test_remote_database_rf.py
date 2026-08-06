from __future__ import annotations

from ir_rf_hub.esphome.remote_database import lookup_bundled_rf, search_bundled
from ir_rf_hub.esphome.rf_protocol_decode import DecodedRfSignal, decode_came, encode_came


def test_search_bundled_rf_finds_a_real_came_entry():
    # Real Sub-GHz/Ceiling_Fans code from UberGuidoZ/Flipper, bundled via
    # remote_database_build.py's fetch_flipper_subghz.
    results = search_bundled("ceiling fan high", signal_type="rf")
    assert results, "expected at least one RF match"
    assert results[0].protocol == "CAME"
    assert all(r.protocol in ("Princeton", "CAME") for r in results)


def test_search_bundled_rf_excludes_ir_protocols():
    results = search_bundled("power", signal_type="rf", limit=200)
    assert all(r.protocol in ("Princeton", "CAME") for r in results)


def test_search_bundled_ir_excludes_rf_protocols():
    results = search_bundled("fan", signal_type="ir", limit=200)
    assert all(r.protocol in ("NEC", "NECext") for r in results)


def test_search_result_round_trips_through_came_encoder():
    results = search_bundled("ceiling fan high", signal_type="rf")
    match = next(r for r in results if r.protocol == "CAME")
    timings = encode_came(match.address_bytes, bit_count=int(match.command_bytes))
    decoded = decode_came(timings)
    assert decoded is not None
    assert decoded.key_hex == match.address_bytes


def test_lookup_bundled_rf_finds_a_real_entry():
    decoded = DecodedRfSignal(protocol="CAME", key_hex="00 00 00 00 00 00 00 5F", bit_count=12, te_us=320)
    matches = lookup_bundled_rf(decoded)
    assert any(m.category == "Ceiling_Fans" for m in matches)
    assert all(m.source == "bundled" for m in matches)


def test_lookup_bundled_rf_empty_for_unindexed_protocol():
    decoded = DecodedRfSignal(protocol="KeeLoq", key_hex="00 00 00 00 00 00 00 01", bit_count=64, te_us=400)
    assert lookup_bundled_rf(decoded) == []
