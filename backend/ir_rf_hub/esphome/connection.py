"""Thin per-device wrapper around aioesphomeapi.APIClient, scoped to exactly
what ir_rf_proxy needs. See tests/fakes/fake_esphome_server.py for the wire
details this was verified against (method names, field shapes, capability
bitmasks).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

import aioesphomeapi as api

from ir_rf_hub.db.models import DeviceRole, SignalDomain

logger = logging.getLogger(__name__)

# InfraredCapability / RadioFrequencyCapability share the same bit layout.
_CAP_TRANSMITTER = 1
_CAP_RECEIVER = 2


@dataclass
class DiscoveredEntity:
    esphome_key: int
    object_id: str
    domain: SignalDomain
    role: DeviceRole
    frequency_hz: int | None


class DeviceUnreachableError(Exception):
    pass


class EspHomeConnection:
    """One live native-API connection to one ESPHome device."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        password: str | None = None,
        noise_psk: str | None = None,
        connect_timeout_s: int = 10,
    ) -> None:
        self._client = api.APIClient(host, port, password=password, noise_psk=noise_psk)
        self._connect_timeout_s = connect_timeout_s
        self._receive_listeners: dict[int, list[Callable[[list[int]], None]]] = {}
        self._receive_unsub: Callable[[], None] | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        try:
            await asyncio.wait_for(self._client.connect(login=False), timeout=self._connect_timeout_s)
        except (asyncio.TimeoutError, api.APIConnectionError) as exc:
            raise DeviceUnreachableError(str(exc)) from exc
        self._receive_unsub = self._client.subscribe_infrared_rf_receive(self._on_receive_event)
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        if self._receive_unsub is not None:
            self._receive_unsub()
            self._receive_unsub = None
        try:
            await self._client.disconnect()
        except Exception:  # noqa: BLE001 -- best-effort on the way down
            logger.debug("Error during disconnect, ignoring", exc_info=True)

    def _on_receive_event(self, event: api.InfraredRFReceiveEvent) -> None:
        for callback in list(self._receive_listeners.get(event.key, [])):
            callback(list(event.timings))

    def add_receive_listener(self, esphome_key: int, callback: Callable[[list[int]], None]) -> Callable[[], None]:
        """Register a callback for raw receive events on one entity key.
        Returns an unsubscribe function.
        """
        self._receive_listeners.setdefault(esphome_key, []).append(callback)

        def _unsubscribe() -> None:
            listeners = self._receive_listeners.get(esphome_key)
            if listeners and callback in listeners:
                listeners.remove(callback)

        return _unsubscribe

    async def device_info(self) -> api.DeviceInfo:
        try:
            return await asyncio.wait_for(self._client.device_info(), timeout=self._connect_timeout_s)
        except (asyncio.TimeoutError, api.APIConnectionError) as exc:
            raise DeviceUnreachableError(str(exc)) from exc

    async def list_entities(self) -> list[DiscoveredEntity]:
        """Discover ir_rf_proxy entities and split them into one row per
        capability bit -- InfraredCapability/RadioFrequencyCapability are
        bitmasks, so a future entity advertising both TRANSMITTER and
        RECEIVER on one key correctly yields two DeviceEntity rows sharing
        that key, rather than being silently dropped to one role.
        """
        try:
            entities, _services = await asyncio.wait_for(
                self._client.list_entities_services(), timeout=self._connect_timeout_s
            )
        except (asyncio.TimeoutError, api.APIConnectionError) as exc:
            raise DeviceUnreachableError(str(exc)) from exc

        discovered: list[DiscoveredEntity] = []
        for entity in entities:
            if isinstance(entity, api.InfraredInfo):
                domain = SignalDomain.infrared
                # receiver_frequency is the RX demodulation carrier hint
                # (e.g. 38kHz); it isn't meaningful for a TX-role entity.
                frequency_hz = entity.receiver_frequency or None
            elif isinstance(entity, api.RadioFrequencyInfo):
                domain = SignalDomain.radio_frequency
                # frequency_min/frequency_max describe a supported range;
                # for the common fixed-frequency setup (one ir_rf_proxy
                # entry per band) these are equal, so frequency_min is a
                # reasonable default carrier for commands recorded against
                # this entity. A genuinely wideband receiver isn't fully
                # modeled here -- see plan's open items.
                frequency_hz = entity.frequency_min or None
            else:
                continue

            if entity.capabilities & _CAP_TRANSMITTER:
                discovered.append(
                    DiscoveredEntity(entity.key, entity.object_id, domain, DeviceRole.tx, frequency_hz)
                )
            if entity.capabilities & _CAP_RECEIVER:
                discovered.append(
                    DiscoveredEntity(entity.key, entity.object_id, domain, DeviceRole.rx, frequency_hz)
                )
        return discovered

    def transmit_infrared(self, *, key: int, carrier_frequency: int, timings: list[int], repeat_count: int = 1) -> None:
        self._client.infrared_rf_transmit_raw_timings(
            key=key, carrier_frequency=carrier_frequency, timings=timings, repeat_count=repeat_count
        )

    def transmit_radio_frequency(
        self,
        *,
        key: int,
        frequency: int,
        timings: list[int],
        repeat_count: int = 1,
        modulation: api.RadioFrequencyModulation = api.RadioFrequencyModulation.OOK,
    ) -> None:
        self._client.radio_frequency_transmit_raw_timings(
            key=key, frequency=frequency, timings=timings, modulation=modulation, repeat_count=repeat_count
        )
