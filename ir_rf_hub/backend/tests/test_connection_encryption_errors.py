"""EspHomeConnection.connect()'s exception mapping -- verified against
aioesphomeapi's real exception hierarchy (see connection.py's comment on
why the specific except clauses must precede the generic one). The fake
ESPHome test server used everywhere else in this suite is plaintext-only
and doesn't implement a Noise handshake at all, so these can't be
exercised through a real connection -- mocking aioesphomeapi.APIClient's
connect() directly is the only deterministic way to trigger each one.
"""

from __future__ import annotations

import aioesphomeapi as api
import pytest

from ir_rf_hub.esphome.connection import (
    DeviceEncryptionKeyInvalidError,
    DeviceRequiresEncryptionError,
    DeviceUnexpectedEncryptionError,
    DeviceUnreachableError,
    EspHomeConnection,
)


async def _connect_with_mocked_error(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    async def fake_connect(self, *, login: bool = False) -> None:
        raise exc

    monkeypatch.setattr(api.APIClient, "connect", fake_connect)
    conn = EspHomeConnection(host="10.0.0.1", port=6053)
    await conn.connect()


async def test_requires_encryption_error_maps_to_specific_exception(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(DeviceRequiresEncryptionError):
        await _connect_with_mocked_error(monkeypatch, api.RequiresEncryptionAPIError())


async def test_invalid_encryption_key_error_maps_to_specific_exception(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(DeviceEncryptionKeyInvalidError):
        await _connect_with_mocked_error(monkeypatch, api.InvalidEncryptionKeyAPIError())


async def test_encryption_hello_error_also_maps_to_key_invalid(monkeypatch: pytest.MonkeyPatch):
    # A less specific encryption-handshake failure -- bucketed with "wrong
    # key" since that's overwhelmingly the real-world cause.
    with pytest.raises(DeviceEncryptionKeyInvalidError):
        await _connect_with_mocked_error(monkeypatch, api.EncryptionHelloAPIError())


async def test_encryption_plaintext_error_maps_to_unexpected_encryption(monkeypatch: pytest.MonkeyPatch):
    # The reverse case: we sent a key, but the device answered in
    # plaintext -- it isn't actually using encryption.
    with pytest.raises(DeviceUnexpectedEncryptionError):
        await _connect_with_mocked_error(monkeypatch, api.EncryptionPlaintextAPIError())


async def test_generic_connection_error_maps_to_base_unreachable_only(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(DeviceUnreachableError) as exc_info:
        await _connect_with_mocked_error(monkeypatch, api.SocketAPIError("connection refused"))
    assert not isinstance(
        exc_info.value,
        (DeviceRequiresEncryptionError, DeviceEncryptionKeyInvalidError, DeviceUnexpectedEncryptionError),
    )


async def test_timeout_maps_to_base_unreachable_only(monkeypatch: pytest.MonkeyPatch):
    async def fake_connect(self, *, login: bool = False) -> None:
        raise TimeoutError("did not respond")

    monkeypatch.setattr(api.APIClient, "connect", fake_connect)
    conn = EspHomeConnection(host="10.0.0.1", port=6053, connect_timeout_s=1)
    with pytest.raises(DeviceUnreachableError) as exc_info:
        await conn.connect()
    assert not isinstance(
        exc_info.value,
        (DeviceRequiresEncryptionError, DeviceEncryptionKeyInvalidError, DeviceUnexpectedEncryptionError),
    )
