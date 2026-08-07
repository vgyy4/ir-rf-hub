"""Decodes raw mark/space timings into a (protocol, address, command)
triple for well-known consumer IR encodings, when a capture cleanly
matches one. Purely structural decoding -- this says "this is NEC,
address 0x00DF, command 0x1CE3", never "this is a Samsung TV remote"
(that's flipper_irdb.py's job, built on top of this).

NEC/NECext's `address_bytes`/`command_bytes` are deliberately formatted to
match the flipper-format `.ir` file convention exactly (four
space-separated uppercase hex bytes, e.g. "00 DF 00 00") -- that's what
lets flipper_irdb.py's bundled index, built from real Flipper-format
files, be looked up directly by these fields with no re-encoding step.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DecodedSignal:
    protocol: str  # "NEC" | "NECext" | "SIRC" | "SIRC15" | "SIRC20"
    address: int
    command: int
    # Only meaningful for NEC/NECext -- "" for protocols that don't have a
    # Flipper-format equivalent wired up (see flipper_irdb.py).
    address_bytes: str = ""
    command_bytes: str = ""


def _flipper_hex(byte0: int, byte1: int) -> str:
    return f"{byte0:02X} {byte1:02X} 00 00"


def _byte_from_bits(bits: list[int]) -> int:
    # LSB first, per NEC/SIRC's own bit order.
    return sum(bit << i for i, bit in enumerate(bits))


# --- NEC family ----------------------------------------------------------
# Timings: header mark+space, then 32 data bits as (mark, space) pairs --
# mark is ~constant, space encodes the bit (pulse-distance encoding).
# https://www.sbprojects.net/knowledge/ir/nec.php
_NEC_HEADER_MARK = (7500, 10500)
_NEC_HEADER_SPACE = (3800, 5200)
_NEC_BIT_MARK = (300, 800)
_NEC_ZERO_SPACE = (300, 800)
_NEC_ONE_SPACE = (1300, 2000)


def _decode_nec_bits(body: list[int]) -> list[int] | None:
    bits: list[int] = []
    i = 0
    while len(bits) < 32 and i + 1 < len(body):
        mark, space = body[i], body[i + 1]
        if not (_NEC_BIT_MARK[0] <= mark <= _NEC_BIT_MARK[1]):
            return None
        if _NEC_ZERO_SPACE[0] <= -space <= _NEC_ZERO_SPACE[1]:
            bits.append(0)
        elif _NEC_ONE_SPACE[0] <= -space <= _NEC_ONE_SPACE[1]:
            bits.append(1)
        else:
            return None
        i += 2
    return bits if len(bits) == 32 else None


_NEC_HEADER_TIMINGS = (9000, -4500)
_NEC_ZERO_BIT_TIMINGS = (562, -562)
_NEC_ONE_BIT_TIMINGS = (562, -1687)
_NEC_TRAILING_MARK = 562


def encode_nec(address_bytes: str, command_bytes: str) -> list[int]:
    """Inverse of decode_nec -- renders Flipper-format address/command byte
    strings (e.g. "00 DF 00 00", the same format remote_database.py's
    bundled index stores) back into a fireable raw timing list: header, the
    same 4 data bytes decode_nec reads (address low/high, command
    low/high), and a trailing mark to close the frame, matching how a real
    NEC transmitter -- and ir_rf_proxy -- ends a burst. Only the first two
    space-separated bytes of each string are meaningful (see
    protocol_decode.py's module docstring); the trailing "00 00" is always
    padding in the bundled dataset.
    """
    addr, addr_inv = (int(b, 16) for b in address_bytes.split()[:2])
    cmd, cmd_inv = (int(b, 16) for b in command_bytes.split()[:2])

    timings = list(_NEC_HEADER_TIMINGS)
    for byte in (addr, addr_inv, cmd, cmd_inv):
        for bit_index in range(8):  # LSB first, matching decode_nec's own bit order
            bit = (byte >> bit_index) & 1
            timings.extend(_NEC_ONE_BIT_TIMINGS if bit else _NEC_ZERO_BIT_TIMINGS)
    timings.append(_NEC_TRAILING_MARK)
    return timings


def decode_nec(timings: list[int]) -> DecodedSignal | None:
    if len(timings) < 2:
        return None
    header_mark, header_space = timings[0], timings[1]
    if not (_NEC_HEADER_MARK[0] <= header_mark <= _NEC_HEADER_MARK[1]):
        return None
    if not (_NEC_HEADER_SPACE[0] <= -header_space <= _NEC_HEADER_SPACE[1]):
        return None

    bits = _decode_nec_bits(timings[2:])
    if bits is None:
        return None

    addr, addr_inv, cmd, cmd_inv = (_byte_from_bits(bits[i : i + 8]) for i in range(0, 32, 8))
    # Classic NEC redundantly repeats each byte's bitwise complement as a
    # cheap integrity check, freeing up no extra address space; "extended"
    # NEC (NECext) drops that redundancy for a real 16-bit address instead.
    # Whether *either* check fails is enough to call it NECext -- Flipper's
    # own convention (confirmed against real Flipper-IRDB samples) still
    # packs both fields as raw 16-bit pairs either way.
    is_standard = addr_inv == (~addr & 0xFF) and cmd_inv == (~cmd & 0xFF)
    protocol = "NEC" if is_standard else "NECext"
    address = addr if is_standard else (addr | (addr_inv << 8))
    command = cmd if is_standard else (cmd | (cmd_inv << 8))
    return DecodedSignal(
        protocol=protocol,
        address=address,
        command=command,
        address_bytes=_flipper_hex(addr, addr_inv),
        command_bytes=_flipper_hex(cmd, cmd_inv),
    )


# --- Sony SIRC -------------------------------------------------------------
# Timings: header mark, then N data bits as (mark, space) pairs -- mark
# duration encodes the bit this time (pulse-width encoding), space is a
# roughly-constant gap. 12/15/20 bits depending on device family.
# https://www.sbprojects.net/knowledge/ir/sirc.php
_SIRC_HEADER_MARK = (2000, 2800)
_SIRC_ZERO_MARK = (400, 800)
_SIRC_ONE_MARK = (1000, 1400)
_SIRC_BIT_LENGTHS = (12, 15, 20)
_SIRC_PROTOCOL_NAMES = {12: "SIRC", 15: "SIRC15", 20: "SIRC20"}


def decode_sirc(timings: list[int]) -> DecodedSignal | None:
    if len(timings) < 4:
        return None
    if not (_SIRC_HEADER_MARK[0] <= timings[0] <= _SIRC_HEADER_MARK[1]):
        return None

    body = timings[1:]
    bits: list[int] = []
    i = 0
    while i < len(body):
        mark = body[i]
        if _SIRC_ZERO_MARK[0] <= mark <= _SIRC_ZERO_MARK[1]:
            bits.append(0)
        elif _SIRC_ONE_MARK[0] <= mark <= _SIRC_ONE_MARK[1]:
            bits.append(1)
        else:
            break
        i += 2  # skip the following (roughly-constant) space
    if len(bits) not in _SIRC_BIT_LENGTHS:
        return None

    command = _byte_from_bits(bits[:7])
    address = _byte_from_bits(bits[7:])
    return DecodedSignal(protocol=_SIRC_PROTOCOL_NAMES[len(bits)], address=address, command=command)


_DECODERS = (decode_nec, decode_sirc)


def decode_signal(timings: list[int]) -> DecodedSignal | None:
    """Tries each known decoder in turn; None if nothing recognized the
    shape. Cheap and side-effect-free enough to call on every stop_recording
    -- see api/rest/recording.py."""
    for decoder in _DECODERS:
        result = decoder(timings)
        if result is not None:
            return result
    return None
