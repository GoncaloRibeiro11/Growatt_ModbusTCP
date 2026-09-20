"""MIN TL-XH priority control and diagnostic readback must describe one state."""
from __future__ import annotations

import importlib

import pytest

_const = importlib.import_module("growatt_under_test.const")
_gm = importlib.import_module("growatt_under_test.growatt_modbus")


class FakeHoldingReads:
    """Return the requested 3018 value and harmless zeroes for other reads."""

    def __init__(self, priority_mode: int):
        self.priority_mode = priority_mode

    def __call__(self, start_address: int, count: int) -> list[int]:
        if start_address == 3018:
            return [self.priority_mode]
        return [0] * count


@pytest.mark.parametrize(
    ("raw_value", "standard_value"),
    [(0, 0), (2, 1), (3, 2)],
)
def test_min_tl_xh_priority_sensor_follows_register_3018(raw_value, standard_value):
    """The generic sensor must not stay at its default Load First value."""
    client = _gm.GrowattModbus.__new__(_gm.GrowattModbus)
    client.register_map_name = "TEST_MIN_TL_XH"
    client.register_map = {
        "holding_registers": {
            3018: {"name": "tl_xh_priority_mode", "maps_to": "priority_mode"},
        },
    }
    client.read_holding_registers = FakeHoldingReads(raw_value)
    data = _gm.GrowattData()

    client._read_device_info(data)

    assert data.tl_xh_priority_mode == raw_value
    assert data.priority_mode == standard_value


def test_min_tl_xh_profile_declares_both_priority_fields_as_backed_by_3018():
    """Diagnostics must identify priority_mode as a reading rather than a default."""
    register_map = _const.REGISTER_MAPS["MIN_TL_XH_3000_10000_V201"]
    register = register_map["holding_registers"][3018]

    assert register["name"] == "tl_xh_priority_mode"
    assert register["maps_to"] == "priority_mode"
    assert {"tl_xh_priority_mode", "priority_mode"}.issubset(
        _const.profile_register_names(register_map)
    )
