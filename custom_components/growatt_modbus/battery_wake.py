"""Short VPP charge pulse used to wake sleeping APX batteries."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

from .coordinator import GrowattModbusCoordinator
from .growatt_modbus import ModbusWriteError

_LOGGER = logging.getLogger(__name__)

VPP_CONTROL_AUTHORITY = 30100
VPP_REMOTE_POWER_ENABLE = 30407
VPP_REMOTE_POWER_DURATION = 30408
VPP_REMOTE_POWER_PERCENT = 30409
VPP_AC_CHARGE_ENABLE = 30410

WAKE_POWER_PERCENT = 5
WAKE_DURATION_MINUTES = 1
WAKE_PULSE_SECONDS = 12
AC_CHARGE_PRIORITY = 2


class BatteryWakeError(Exception):
    """Raised when a sleeping battery could not be woken safely."""


def is_tl_xh_battery_wake_supported(coordinator: GrowattModbusCoordinator) -> bool:
    """Return whether this is a MIN/TL-XH profile with the confirmed mode register."""
    client = coordinator.modbus_client
    if client is None:
        return False

    holding_registers = client.register_map.get("holding_registers", {})
    register_map_name = str(client.register_map.get("name", "")).lower()
    return 3018 in holding_registers and "tl-xh" in register_map_name


async def async_wake_tl_xh_battery(
    hass: HomeAssistant,
    coordinator: GrowattModbusCoordinator,
) -> None:
    """Wake an APX battery with a short, automatically released charge request.

    APX is woken by the inverter's hardware WAKE line. A real charge request makes
    the inverter assert that line; changing priority register 3018 alone may not.
    The pulse uses a low power request and always disables the remote override.
    """
    if not is_tl_xh_battery_wake_supported(coordinator):
        raise BatteryWakeError("Battery wake is only available for MIN/TL-XH profiles")

    lock = getattr(coordinator, "_tl_xh_battery_wake_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        coordinator._tl_xh_battery_wake_lock = lock

    if lock.locked():
        _LOGGER.debug("TL-XH battery wake pulse is already running")
        return

    client = coordinator.modbus_client
    async with lock:
        try:
            current_authority = await hass.async_add_executor_job(
                client.read_holding_registers,
                VPP_CONTROL_AUTHORITY,
                1,
            )
            current_remote = await hass.async_add_executor_job(
                client.read_holding_registers,
                VPP_REMOTE_POWER_ENABLE,
                4,
            )
        except Exception as exc:
            raise BatteryWakeError(
                "The inverter did not expose VPP wake registers 30407-30410"
            ) from exc

        if current_authority is None or len(current_authority) < 1:
            raise BatteryWakeError(
                "The inverter did not expose VPP control authority register 30100"
            )

        if current_remote is None or len(current_remote) < 4:
            raise BatteryWakeError(
                "The inverter did not expose VPP wake registers 30407-30410"
            )

        if int(current_remote[0]) == 1:
            raise BatteryWakeError(
                "Remote battery control is already active; the wake pulse was not applied"
            )

        pulse_started = False
        try:
            writes = [
                (VPP_AC_CHARGE_ENABLE, AC_CHARGE_PRIORITY),
                (VPP_REMOTE_POWER_DURATION, WAKE_DURATION_MINUTES),
                (VPP_REMOTE_POWER_PERCENT, WAKE_POWER_PERCENT),
                (VPP_REMOTE_POWER_ENABLE, 1),
            ]
            if int(current_authority[0]) != 1:
                writes.insert(0, (VPP_CONTROL_AUTHORITY, 1))

            # Cleanup is required after the first attempted write because the
            # preparatory duration/power registers may already have changed.
            pulse_started = True
            for register, value in writes:
                written = await hass.async_add_executor_job(
                    client.write_register,
                    register,
                    value,
                )
                if not written:
                    raise BatteryWakeError(
                        f"The inverter rejected battery wake register {register}"
                    )

            _LOGGER.info(
                "Started TL-XH APX wake pulse at %d%% for %d seconds",
                WAKE_POWER_PERCENT,
                WAKE_PULSE_SECONDS,
            )
            await asyncio.sleep(WAKE_PULSE_SECONDS)
        except ModbusWriteError as exc:
            raise BatteryWakeError("The inverter rejected the battery wake pulse") from exc
        finally:
            if pulse_started:
                release_error = None
                stopped_successfully = False
                try:
                    stopped = await hass.async_add_executor_job(
                        client.write_register,
                        VPP_REMOTE_POWER_ENABLE,
                        0,
                    )
                    if not stopped:
                        release_error = "the remote power command could not be disabled"
                    else:
                        stopped_successfully = True
                        _LOGGER.info("Released TL-XH APX wake pulse")
                except ModbusWriteError as exc:
                    _LOGGER.error("Failed to release TL-XH APX wake pulse")
                    release_error = f"the remote power command could not be disabled: {exc}"

                # Restore the previous parameters only after 30407=0 is confirmed.
                # If stopping failed, keep the safer 5%/1-minute request in place.
                if stopped_successfully:
                    try:
                        restored = await hass.async_add_executor_job(
                            client.write_registers,
                            VPP_REMOTE_POWER_DURATION,
                            [int(value) for value in current_remote[1:4]],
                        )
                        if not restored:
                            _LOGGER.warning("Could not restore VPP wake parameter registers 30408-30410")
                    except ModbusWriteError:
                        _LOGGER.warning(
                            "Could not restore VPP wake parameter registers 30408-30410",
                            exc_info=True,
                        )

                    if int(current_authority[0]) != 1:
                        try:
                            restored = await hass.async_add_executor_job(
                                client.write_registers,
                                VPP_CONTROL_AUTHORITY,
                                [int(current_authority[0])],
                            )
                            if not restored:
                                _LOGGER.warning("Could not restore VPP control authority register 30100")
                        except ModbusWriteError:
                            _LOGGER.warning(
                                "Could not restore VPP control authority register 30100",
                                exc_info=True,
                            )

                if release_error is not None:
                    raise BatteryWakeError(
                        f"The battery wake pulse started but {release_error}"
                    )

        await coordinator.async_request_refresh()
