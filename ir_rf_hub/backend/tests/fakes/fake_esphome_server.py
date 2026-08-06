"""A minimal fake ESPHome native-API server, speaking the real plaintext
wire protocol (varint-framed protobuf, no Noise encryption) using the
actual generated `aioesphomeapi.api_pb2` message classes -- so the real
`aioesphomeapi.APIClient` can connect to it unmodified. This is what
unblocks every later phase's automated tests without needing physical
ESPHome hardware.

Protocol details below were confirmed by inspecting the installed
aioesphomeapi package directly (see the design conversation for the
inspection commands), not guessed:

- Plaintext framing: [0x00 preamble][varint length][varint msg_type][payload].
  `aioesphomeapi._frame_helper.packets.make_plain_text_packets` builds this
  exact format, so we reuse it for encoding server->client frames rather
  than reimplementing it.
- Handshake is just HelloRequest -> HelloResponse; APIClient.connect() only
  sends an AuthenticationRequest when `login=True` is passed, which our
  connection.py (Phase 1) does not need to do since the fake/dev devices
  here have no password configured.
- `list_entities_services()` sends ListEntitiesRequest and expects a stream
  of ListEntities<Domain>Response messages terminated by
  ListEntitiesDoneResponse.
- IR and RF raw receive both arrive as the *same* message type,
  InfraredRFReceiveEvent(device_id, key, timings), pushed unsolicited by
  the device at any time -- there is no explicit subscribe request on the
  wire, `subscribe_infrared_rf_receive()` just registers a local callback
  for that message type. This confirms reception is always-on at the
  ESPHome/API level, matching the "no log scraping needed" design.
- Both `infrared_rf_transmit_raw_timings()` and
  `radio_frequency_transmit_raw_timings()` send the same fire-and-forget
  InfraredRFTransmitRawTimingsRequest message (no ack) -- `modulation` is
  simply unset/ignored for the IR case.
- Wire message-type IDs (from aioesphomeapi.core.MESSAGE_TYPE_TO_PROTO, which
  is keyed by the *actual* 1-indexed wire ID -- confirmed against a real raw
  packet capture, since a sibling table in the same module,
  MESSAGE_NUMBER_TO_PROTO, is a 0-indexed array offset by one from the wire
  ID and is easy to misread as the wire table by mistake):
  HelloRequest=1, HelloResponse=2, DisconnectRequest=5, DisconnectResponse=6,
  PingRequest=7, PingResponse=8, DeviceInfoRequest=9, DeviceInfoResponse=10,
  ListEntitiesRequest=11, ListEntitiesDoneResponse=19,
  ListEntitiesInfraredResponse=135, InfraredRFTransmitRawTimingsRequest=136,
  InfraredRFReceiveEvent=137, ListEntitiesRadioFrequencyResponse=148.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from aioesphomeapi import api_pb2 as pb
from aioesphomeapi._frame_helper.packets import make_plain_text_packets

logger = logging.getLogger(__name__)

MSG_HELLO_REQUEST = 1
MSG_HELLO_RESPONSE = 2
MSG_DISCONNECT_REQUEST = 5
MSG_DISCONNECT_RESPONSE = 6
MSG_PING_REQUEST = 7
MSG_PING_RESPONSE = 8
MSG_DEVICE_INFO_REQUEST = 9
MSG_DEVICE_INFO_RESPONSE = 10
MSG_LIST_ENTITIES_REQUEST = 11
MSG_LIST_ENTITIES_DONE_RESPONSE = 19
MSG_LIST_ENTITIES_INFRARED_RESPONSE = 135
MSG_INFRARED_RF_TRANSMIT_RAW_TIMINGS_REQUEST = 136
MSG_INFRARED_RF_RECEIVE_EVENT = 137
MSG_LIST_ENTITIES_RADIO_FREQUENCY_RESPONSE = 148

# msg_type -> protobuf class, for decoding incoming frames. Only messages a
# client actually sends need to be here.
_INCOMING: dict[int, type] = {
    MSG_HELLO_REQUEST: pb.HelloRequest,
    MSG_DISCONNECT_REQUEST: pb.DisconnectRequest,
    MSG_PING_REQUEST: pb.PingRequest,
    MSG_DEVICE_INFO_REQUEST: pb.DeviceInfoRequest,
    MSG_LIST_ENTITIES_REQUEST: pb.ListEntitiesRequest,
    MSG_INFRARED_RF_TRANSMIT_RAW_TIMINGS_REQUEST: pb.InfraredRFTransmitRawTimingsRequest,
}


@dataclass
class FakeInfraredEntity:
    key: int
    object_id: str
    name: str
    capabilities: int  # bitmask: 1=TRANSMITTER, 2=RECEIVER
    receiver_frequency: int = 0


@dataclass
class FakeRadioFrequencyEntity:
    key: int
    object_id: str
    name: str
    capabilities: int
    frequency_min: int = 300_000_000
    frequency_max: int = 928_000_000
    supported_modulations: int = 1  # bitmask, bit 0 = OOK


@dataclass
class TransmitCall:
    key: int
    carrier_frequency: int
    timings: list[int]
    repeat_count: int
    modulation: int
    device_id: int = 0


@dataclass
class FakeEspHomeServer:
    """One instance = one simulated ESPHome device."""

    name: str = "fake-esphome"
    mac_address: str = "AA:BB:CC:DD:EE:FF"
    infrared_entities: list[FakeInfraredEntity] = field(default_factory=list)
    radio_frequency_entities: list[FakeRadioFrequencyEntity] = field(default_factory=list)

    host: str = "127.0.0.1"
    port: int = 0  # 0 = ask the OS for a free port

    def __post_init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self.transmitted: list[TransmitCall] = []

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        logger.info("FakeEspHomeServer '%s' listening on %s:%s", self.name, self.host, self.port)

    async def stop(self) -> None:
        for writer in list(self._writers):
            writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def __aenter__(self) -> FakeEspHomeServer:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.stop()

    def _write(self, writer: asyncio.StreamWriter, msg_type: int, message) -> None:
        # make_plain_text_packets returns a list of byte chunks (preamble,
        # length varint, msg_type varint, payload) meant for writelines(),
        # not a single bytes object.
        frame = make_plain_text_packets([(msg_type, message.SerializeToString())])
        writer.writelines(frame)

    async def emit_receive_event(self, *, key: int, timings: list[int], device_id: int = 0) -> None:
        """Push an unsolicited InfraredRFReceiveEvent to every connected
        client -- simulates a real remote being pressed in front of the
        device's receiver, for scripting recording-flow tests.
        """
        event = pb.InfraredRFReceiveEvent(device_id=device_id, key=key, timings=timings)
        for writer in list(self._writers):
            self._write(writer, MSG_INFRARED_RF_RECEIVE_EVENT, event)
            try:
                await writer.drain()
            except ConnectionError:
                self._writers.discard(writer)

    async def _read_varuint(self, reader: asyncio.StreamReader) -> int:
        result = 0
        bitpos = 0
        while True:
            byte = await reader.readexactly(1)
            val = byte[0]
            result |= (val & 0x7F) << bitpos
            if (val & 0x80) == 0:
                return result
            bitpos += 7

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        peer = writer.get_extra_info("peername")
        logger.debug("Client connected: %s", peer)
        try:
            while True:
                preamble = await reader.readexactly(1)
                if preamble != b"\x00":
                    logger.warning("Unexpected preamble %r from %s, closing", preamble, peer)
                    return
                length = await self._read_varuint(reader)
                msg_type = await self._read_varuint(reader)
                payload = await reader.readexactly(length) if length else b""
                await self._dispatch(writer, msg_type, payload)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()
            logger.debug("Client disconnected: %s", peer)

    async def _dispatch(self, writer: asyncio.StreamWriter, msg_type: int, payload: bytes) -> None:
        cls = _INCOMING.get(msg_type)
        if cls is None:
            logger.debug("Ignoring unhandled incoming msg_type=%s", msg_type)
            return
        message = cls()
        message.ParseFromString(payload)

        if msg_type == MSG_HELLO_REQUEST:
            resp = pb.HelloResponse(
                api_version_major=1, api_version_minor=14, server_info="fake-esphome", name=self.name
            )
            self._write(writer, MSG_HELLO_RESPONSE, resp)

        elif msg_type == MSG_DEVICE_INFO_REQUEST:
            resp = pb.DeviceInfoResponse(
                uses_password=False,
                name=self.name,
                mac_address=self.mac_address,
                esphome_version="2026.1.0",
                model="fake-esp32",
                friendly_name=self.name,
            )
            self._write(writer, MSG_DEVICE_INFO_RESPONSE, resp)

        elif msg_type == MSG_LIST_ENTITIES_REQUEST:
            for ir in self.infrared_entities:
                resp = pb.ListEntitiesInfraredResponse(
                    object_id=ir.object_id,
                    key=ir.key,
                    name=ir.name,
                    capabilities=ir.capabilities,
                    receiver_frequency=ir.receiver_frequency,
                )
                self._write(writer, MSG_LIST_ENTITIES_INFRARED_RESPONSE, resp)
            for rf in self.radio_frequency_entities:
                resp = pb.ListEntitiesRadioFrequencyResponse(
                    object_id=rf.object_id,
                    key=rf.key,
                    name=rf.name,
                    capabilities=rf.capabilities,
                    frequency_min=rf.frequency_min,
                    frequency_max=rf.frequency_max,
                    supported_modulations=rf.supported_modulations,
                )
                self._write(writer, MSG_LIST_ENTITIES_RADIO_FREQUENCY_RESPONSE, resp)
            self._write(writer, MSG_LIST_ENTITIES_DONE_RESPONSE, pb.ListEntitiesDoneResponse())

        elif msg_type == MSG_PING_REQUEST:
            self._write(writer, MSG_PING_RESPONSE, pb.PingResponse())

        elif msg_type == MSG_DISCONNECT_REQUEST:
            self._write(writer, MSG_DISCONNECT_RESPONSE, pb.DisconnectResponse())

        elif msg_type == MSG_INFRARED_RF_TRANSMIT_RAW_TIMINGS_REQUEST:
            self.transmitted.append(
                TransmitCall(
                    key=message.key,
                    carrier_frequency=message.carrier_frequency,
                    timings=list(message.timings),
                    repeat_count=message.repeat_count or 1,
                    modulation=message.modulation,
                    device_id=message.device_id,
                )
            )

        await writer.drain()
