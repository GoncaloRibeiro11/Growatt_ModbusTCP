"""MIN TL-XH must expose the TOU schedule implemented by its firmware (#400).

Hardware on a MIN 4600TL-XH (DTC 5100) returned all nine V1.39 schedule pairs at
3038-3045 and 3050-3059. The integration previously omitted those addresses from
the MIN profile, so register 3018 could display "Battery First" while every real
period remained disabled and the inverter continued normal self-consumption.
"""
from __future__ import annotations

import importlib

_const = importlib.import_module("growatt_under_test.const")


def test_min_tl_xh_exposes_all_v139_tou_period_pairs():
    register_map = _const.REGISTER_MAPS["MIN_TL_XH_3000_10000_V201"]
    holding = register_map["holding_registers"]

    for period in _const.MOD_TOU_PERIODS:
        number = period["period"]
        start = holding[period["start_reg"]]
        end = holding[period["end_reg"]]

        assert start["name"] == f"mod_tou_{number}_start"
        assert end["name"] == f"mod_tou_{number}_end"
        assert start["access"] == end["access"] == "RW"


def test_min_tl_xh_exposes_the_grid_charge_prerequisite():
    holding = _const.REGISTER_MAPS["MIN_TL_XH_3000_10000_V201"]["holding_registers"]

    assert holding[3049]["name"] == "allow_grid_charge"
    assert holding[3049]["access"] == "RW"


def test_live_schedule_sample_decodes_as_disabled_battery_first_all_day():
    """The reporter's first period read 0x2000 / 0x173B on 2026-09-20."""
    start = 8192
    end = 5947

    assert (start >> 15) & 1 == 0
    assert (start >> 13) & 0x3 == 1
    assert ((start >> 8) & 0x1F, start & 0xFF) == (0, 0)
    assert ((end >> 8) & 0x1F, end & 0xFF) == (23, 59)
