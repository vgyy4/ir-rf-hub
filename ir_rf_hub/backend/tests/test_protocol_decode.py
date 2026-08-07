from __future__ import annotations

from ir_rf_hub.esphome.protocol_decode import decode_nec, decode_signal, decode_sirc, encode_nec


def _bits_lsb_first(value: int, width: int) -> list[int]:
    return [(value >> i) & 1 for i in range(width)]


def _nec_signal(addr: int, addr_inv: int, cmd: int, cmd_inv: int) -> list[int]:
    """Builds a synthetic NEC-shaped raw timing list from four literal
    bytes -- mirrors exactly how a real ESPHome capture would look for
    that address/command pair (header, then 32 (mark, space) bit pairs,
    mark ~562us constant, space 562us for a 0 bit or 1687us for a 1 bit).
    """
    timings = [9000, -4500]
    for byte in (addr, addr_inv, cmd, cmd_inv):
        for bit in _bits_lsb_first(byte, 8):
            timings.append(562)
            timings.append(-1687 if bit else -562)
    return timings


def _sirc_signal(command: int, address: int, bits: int) -> list[int]:
    address_width = bits - 7
    timings = [2400]
    for bit in _bits_lsb_first(command, 7) + _bits_lsb_first(address, address_width):
        timings.append(1200 if bit else 600)
        timings.append(-600)
    return timings


def test_decode_nec_standard_address_and_command_inversion_checks_out():
    # addr_inv/cmd_inv are the real complement of addr/cmd -- the classic
    # NEC redundancy check that distinguishes it from NECext.
    signal = _nec_signal(addr=0x04, addr_inv=0xFB, cmd=0x08, cmd_inv=0xF7)
    decoded = decode_nec(signal)
    assert decoded is not None
    assert decoded.protocol == "NEC"
    assert decoded.address == 0x04
    assert decoded.command == 0x08
    assert decoded.address_bytes == "04 FB 00 00"
    assert decoded.command_bytes == "08 F7 00 00"


def test_decode_nec_extended_address_when_inversion_check_fails():
    # Real sample from Flipper-IRDB (TVs/AWA/AWA_MSDV3268O5D0.ir, "Power"):
    # address "00 DF 00 00" -- DF is not ~00, so this is NECext with a
    # real 16-bit address rather than an inverted-redundancy pair. The
    # round-trip through address_bytes/command_bytes reproducing the exact
    # same byte strings is what makes the bundled Flipper index lookup
    # (flipper_irdb.py) work -- it's keyed on these strings verbatim.
    signal = _nec_signal(addr=0x00, addr_inv=0xDF, cmd=0x1C, cmd_inv=0xE3)
    decoded = decode_nec(signal)
    assert decoded is not None
    assert decoded.protocol == "NECext"
    assert decoded.address_bytes == "00 DF 00 00"
    assert decoded.command_bytes == "1C E3 00 00"


def test_decode_nec_rejects_non_nec_shaped_signal():
    assert decode_nec([100, -100, 200, -200]) is None


def test_decode_sirc_12_bit():
    signal = _sirc_signal(command=0x15, address=0x01, bits=12)
    decoded = decode_sirc(signal)
    assert decoded is not None
    assert decoded.protocol == "SIRC"
    assert decoded.command == 0x15
    assert decoded.address == 0x01


def test_decode_sirc_20_bit_extended():
    signal = _sirc_signal(command=0x2A, address=0x1F3, bits=20)
    decoded = decode_sirc(signal)
    assert decoded is not None
    assert decoded.protocol == "SIRC20"
    assert decoded.command == 0x2A
    assert decoded.address == 0x1F3


def test_encode_nec_round_trips_through_decode_nec():
    # Same real Flipper-IRDB sample as test_decode_nec_extended_address_
    # when_inversion_check_fails: encoding it and decoding the result
    # should reproduce the exact same address_bytes/command_bytes -- this
    # is exactly the property the search-and-fire feature depends on
    # (remote_database.py's search results are encoded with this function).
    timings = encode_nec(address_bytes="00 DF 00 00", command_bytes="1C E3 00 00")
    decoded = decode_nec(timings)
    assert decoded is not None
    assert decoded.protocol == "NECext"
    assert decoded.address_bytes == "00 DF 00 00"
    assert decoded.command_bytes == "1C E3 00 00"


def test_encode_nec_produces_a_valid_looking_frame_shape():
    timings = encode_nec(address_bytes="04 FB 00 00", command_bytes="08 F7 00 00")
    assert timings[0] == 9000
    assert timings[1] == -4500
    assert timings[-1] == 562  # trailing mark closes the frame
    assert len(timings) == 2 + 32 * 2 + 1  # header + 32 bits + trailing mark


def test_decode_signal_tries_each_decoder_and_falls_back_to_none():
    nec = _nec_signal(addr=0x01, addr_inv=0xFE, cmd=0x02, cmd_inv=0xFD)
    assert decode_signal(nec).protocol == "NEC"

    sirc = _sirc_signal(command=0x01, address=0x01, bits=12)
    assert decode_signal(sirc).protocol == "SIRC"

    assert decode_signal([1, -1, 2, -2]) is None
