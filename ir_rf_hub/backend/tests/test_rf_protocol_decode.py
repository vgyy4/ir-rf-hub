from __future__ import annotations

from ir_rf_hub.esphome.rf_protocol_decode import (
    decode_came,
    decode_princeton,
    decode_rf_signal,
    encode_came,
    encode_princeton,
)


def test_encode_decode_princeton_round_trips_a_real_sample():
    # Real Sub-GHz/Misc/princeton.sub sample from UberGuidoZ/Flipper:
    # Protocol: Princeton, Bit: 24, Key: 00 00 00 00 00 95 D5 D4, TE: 400.
    timings = encode_princeton("00 00 00 00 00 95 D5 D4", bit_count=24, te_us=400)
    decoded = decode_princeton(timings, te_us=400)
    assert decoded is not None
    assert decoded.protocol == "Princeton"
    assert decoded.bit_count == 24
    assert decoded.key_hex == "00 00 00 00 00 95 D5 D4"


def test_princeton_frame_shape():
    timings = encode_princeton("00 00 00 00 00 00 00 01", bit_count=24, te_us=390)
    # header-free -- straight into 24 bits (48 elements) + stop bit + guard.
    assert len(timings) == 24 * 2 + 2
    assert timings[-2] == 390  # stop bit mark
    assert timings[-1] == -390 * 30  # guard time


def test_decode_princeton_rejects_too_few_bits():
    assert decode_princeton([390, -390] * 5) is None  # only 5 bits, needs 24


def test_encode_decode_came_round_trips_a_real_sample():
    # Real Sub-GHz/Misc/came.sub sample: Protocol: CAME, Bit: 24,
    # Key: 00 00 00 00 00 6A B2 34 (no TE: field in the file -- came.c's
    # own te_short=320 default applies).
    timings = encode_came("00 00 00 00 00 6A B2 34", bit_count=24)
    decoded = decode_came(timings)
    assert decoded is not None
    assert decoded.protocol == "CAME"
    assert decoded.bit_count == 24
    assert decoded.key_hex == "00 00 00 00 00 6A B2 34"


def test_came_frame_starts_with_header_gap_and_start_bit():
    timings = encode_came("00 00 00 00 00 00 00 01", bit_count=24)
    assert timings[0] == -320 * 76  # 24-bit header gap, verbatim from came.c
    assert timings[1] == 320  # start bit


def test_decode_came_rejects_non_came_shaped_signal():
    assert decode_came([100, -100, 200, -200]) is None


def test_decode_rf_signal_tries_each_decoder():
    princeton_timings = encode_princeton("00 00 00 00 00 12 34 56", te_us=390)
    assert decode_rf_signal(princeton_timings).protocol == "Princeton"

    came_timings = encode_came("00 00 00 00 00 12 34 56")
    assert decode_rf_signal(came_timings).protocol == "CAME"

    assert decode_rf_signal([1, -1, 2, -2]) is None
