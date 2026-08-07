"""Search the bundled remote database for a known device's command by
name -- e.g. "samsung tv power" -- as an alternative to recording live or
typing raw timings by hand. See esphome/remote_database.py for the
matching itself; this just adapts it to REST and encodes each result into
a ready-to-fire raw timing list via protocol_decode.encode_nec (IR) or
rf_protocol_decode.encode_princeton/encode_came (RF).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ir_rf_hub.esphome.protocol_decode import encode_nec
from ir_rf_hub.esphome.remote_database import search_bundled
from ir_rf_hub.esphome.rf_protocol_decode import encode_came, encode_princeton
from ir_rf_hub.schemas import RemoteSearchResultSchema

router = APIRouter(prefix="/api/remote-database", tags=["remote-database"])

# The de-facto standard IR carrier -- matches DEFAULT_IR_CARRIER_HZ on the
# frontend, used the same way (there's no receiving entity here to read a
# real carrier from, since these codes never went through a live capture).
_DEFAULT_IR_CARRIER_HZ = 38000


def _encode_result(protocol: str, address_bytes: str, command_bytes: str) -> list[int]:
    if protocol in ("NEC", "NECext"):
        return encode_nec(address_bytes, command_bytes)
    if protocol == "Princeton":
        return encode_princeton(address_bytes, bit_count=int(command_bytes))
    if protocol == "CAME":
        return encode_came(address_bytes, bit_count=int(command_bytes))
    raise HTTPException(500, f"No encoder for protocol {protocol!r}")  # pragma: no cover -- indexed protocols only


@router.get("/search", response_model=list[RemoteSearchResultSchema])
async def search_remote_database(
    q: str = Query(min_length=2), type: str = "ir", limit: int = 30
) -> list[RemoteSearchResultSchema]:
    if type not in ("ir", "rf"):
        raise HTTPException(400, "type must be 'ir' or 'rf'")
    results = search_bundled(q, signal_type=type, limit=limit)
    return [
        RemoteSearchResultSchema(
            category=r.category,
            brand=r.brand,
            model=r.model,
            button=r.button,
            raw_timings=_encode_result(r.protocol, r.address_bytes, r.command_bytes),
            carrier_frequency_hz=_DEFAULT_IR_CARRIER_HZ if type == "ir" else 0,
            repeat_count=1,
        )
        for r in results
    ]
