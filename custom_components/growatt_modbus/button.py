"""Button platform for Growatt Modbus integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .battery_wake import (
    BatteryWakeError,
    async_wake_tl_xh_battery,
    is_tl_xh_battery_wake_supported,
)
from .const import DEVICE_TYPE_BATTERY, DOMAIN
from .coordinator import GrowattModbusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Growatt Modbus button entities."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    if is_tl_xh_battery_wake_supported(coordinator):
        async_add_entities([GrowattWakeBatteryButton(coordinator, config_entry)])


class GrowattWakeBatteryButton(CoordinatorEntity, ButtonEntity):
    """Wake a sleeping APX battery through the inverter's VPP controls."""

    _attr_has_entity_name = True
    _attr_name = "Wake APX Battery"
    _attr_icon = "mdi:battery-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: GrowattModbusCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}_wake_apx_battery"

    @property
    def device_info(self) -> dict[str, Any]:
        """Attach the button to the battery device."""
        return self.coordinator.get_device_info(DEVICE_TYPE_BATTERY)

    async def async_press(self) -> None:
        """Send and safely release the wake pulse."""
        try:
            await async_wake_tl_xh_battery(self.hass, self.coordinator)
        except BatteryWakeError as exc:
            raise HomeAssistantError(str(exc)) from exc
