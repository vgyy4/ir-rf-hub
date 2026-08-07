"""Decodes/encodes raw mark/space timings for well-known fixed-code
sub-GHz RF (OOK) protocols -- the RF equivalent of protocol_decode.py.

Deliberately excludes rolling-code protocols (KeeLoq and similar, common
in car fobs and newer garage openers): a stored code for those is stale
after one real use by design, so there is nothing useful to encode/replay
even with a perfect decoder. Only fixed-code protocols -- the same code
works every time -- are in scope here.

Princeton (PT2262-style) and CAME timing constants and bit encodings are
transcribed directly from Flipper's own firmware source
(flipperdevices/flipperzero-firmware, lib/subghz/protocols/princeton.c
and came.c), not guessed from generic protocol descriptions -- RF timing
conventions vary enough between real implementations that guessing wrong
would silently produce a non-functional code, worse than not supporting
the protocol at all.

Both use the same "Key:" representation Flipper's own .sub files use: an
8-byte (64-bit) big-endian hex string where only the low `bit_count` bits
are significant -- this is what lets rf_database.py's bundled index be
built directly from real .sub files with no re-encoding step, mirroring
protocol_decode.py's address_bytes/command_bytes matching Flipper's own
.ir convention for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecodedRfSignal:
    protocol: str  # "Princeton" | "CAME"
    key_hex: str  # 8 space-separated hex bytes, MSB first (Flipper .sub Key: format)
    bit_count: int
    te_us: int  # base timing unit this particular signal was encoded/decoded at


def _key_hex_to_int(key_hex: str) -> int:
    value = 0
    for byte in key_hex.split():
        value = (value << 8) | int(byte, 16)
    return value


def _int_to_key_hex(value: int) -> str:
    return " ".join(f"{(value >> (8 * i)) & 0xFF:02X}" for i in range(7, -1, -1))


# --- Princeton (PT2262-style) ----------------------------------------------
# lib/subghz/protocols/princeton.c: te_short=390 default, bit "1" = mark
# 3*TE + space 1*TE, bit "0" = mark 1*TE + space 3*TE (MSB first), then a
# stop-bit mark (1*TE) and a guard-time gap (space, 30*TE by default).
_PRINCETON_DEFAULT_TE_US = 390
_PRINCETON_GUARD_TIME_MULTIPLIER = 30
_PRINCETON_MIN_BITS = 24


def encode_princeton(
    key_hex: str, bit_count: int = _PRINCETON_MIN_BITS, te_us: int = _PRINCETON_DEFAULT_TE_US
) -> list[int]:
    value = _key_hex_to_int(key_hex)
    timings: list[int] = []
    for i in range(bit_count - 1, -1, -1):
        bit = (value >> i) & 1
        if bit:
            timings.append(te_us * 3)
            timings.append(-te_us)
        else:
            timings.append(te_us)
            timings.append(-te_us * 3)
    timings.append(te_us)  # stop bit
    timings.append(-te_us * _PRINCETON_GUARD_TIME_MULTIPLIER)  # guard time
    return timings


def decode_princeton(
    timings: list[int], te_us: int = _PRINCETON_DEFAULT_TE_US, tolerance: float = 0.4
) -> DecodedRfSignal | None:
    """Classifies each (mark, space) pair as bit 1 (long mark ~3TE, short
    space ~1TE) or bit 0 (short mark ~1TE, long space ~3TE) until a pair
    that fits neither shape (the stop bit + guard time, or a malformed
    capture) -- mirrors decode_nec's structural, not-full-validation
    approach. Needs at least 24 bits (Princeton's own minimum) to accept.
    """

    def close(value: int, target: int) -> bool:
        return abs(value - target) <= tolerance * target

    bits: list[int] = []
    i = 0
    while i + 1 < len(timings):
        mark, space = timings[i], -timings[i + 1]
        if close(mark, te_us * 3) and close(space, te_us):
            bits.append(1)
        elif close(mark, te_us) and close(space, te_us * 3):
            bits.append(0)
        else:
            break
        i += 2
    if len(bits) < _PRINCETON_MIN_BITS:
        return None

    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return DecodedRfSignal(protocol="Princeton", key_hex=_int_to_key_hex(value), bit_count=len(bits), te_us=te_us)


# --- CAME --------------------------------------------------------------------
# lib/subghz/protocols/came.c: te_short=320, te_long=640 default. Frame is
# a header gap (space, te_short * a per-bit-count multiplier), a start bit
# (mark, te_short), then each data bit as a (space, mark) pair -- SPACE
# first, unlike Princeton -- bit "1" = space te_long + mark te_short, bit
# "0" = space te_short + mark te_long (MSB first). No explicit stop
# bit/guard time is added by the encoder itself.
_CAME_DEFAULT_TE_SHORT_US = 320
_CAME_DEFAULT_TE_LONG_US = 640
# header_te lookup, verbatim from came.c's switch statement (comments
# there give the resulting gap in microseconds at te_short=320).
_CAME_HEADER_TE_MULTIPLIER = {24: 76, 12: 47}
_CAME_MIN_BITS = 12


def encode_came(
    key_hex: str,
    bit_count: int = 24,
    te_short_us: int = _CAME_DEFAULT_TE_SHORT_US,
    te_long_us: int = _CAME_DEFAULT_TE_LONG_US,
) -> list[int]:
    value = _key_hex_to_int(key_hex)
    header_multiplier = _CAME_HEADER_TE_MULTIPLIER.get(bit_count, 16)  # 16 = came.c's "default" fallback
    timings: list[int] = [-te_short_us * header_multiplier, te_short_us]  # header gap, start bit
    for i in range(bit_count - 1, -1, -1):
        bit = (value >> i) & 1
        if bit:
            timings.append(-te_long_us)
            timings.append(te_short_us)
        else:
            timings.append(-te_short_us)
            timings.append(te_long_us)
    return timings


def decode_came(
    timings: list[int],
    te_short_us: int = _CAME_DEFAULT_TE_SHORT_US,
    te_long_us: int = _CAME_DEFAULT_TE_LONG_US,
    tolerance: float = 0.4,
) -> DecodedRfSignal | None:
    """Skips the leading header gap + start bit (by shape, not exact
    duration -- header length varies by bit count, see
    _CAME_HEADER_TE_MULTIPLIER), then classifies each (space, mark) pair
    the same tolerant way decode_princeton does for its (mark, space)
    pairs."""

    def close(value: int, target: int) -> bool:
        return abs(value - target) <= tolerance * target

    if len(timings) < 4:
        return None
    # timings[0] is the header gap (space, large), timings[1] the start
    # bit (mark, ~te_short) -- both skipped by position, not matched.
    if timings[0] >= 0 or not close(timings[1], te_short_us):
        return None

    bits: list[int] = []
    i = 2
    while i + 1 < len(timings):
        space, mark = -timings[i], timings[i + 1]
        if close(space, te_long_us) and close(mark, te_short_us):
            bits.append(1)
        elif close(space, te_short_us) and close(mark, te_long_us):
            bits.append(0)
        else:
            break
        i += 2
    if len(bits) < _CAME_MIN_BITS:
        return None

    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return DecodedRfSignal(protocol="CAME", key_hex=_int_to_key_hex(value), bit_count=len(bits), te_us=te_short_us)


_DECODERS = (decode_princeton, decode_came)


def decode_rf_signal(timings: list[int]) -> DecodedRfSignal | None:
    for decoder in _DECODERS:
        result = decoder(timings)
        if result is not None:
            return result
    return None
