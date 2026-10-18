"""BH1750 ambient light sensor on I2C bus 1 (SDA GPIO2 / pin 3, SCL GPIO3 / pin 5).

Used for automatic panel brightness: dim room -> dim panel, bright room ->
brighter panel, always capped by the user's brightness limit.
Enable I2C first: `sudo raspi-config nonint do_i2c 0`.
"""

from __future__ import annotations

import time

from .pins import BH1750_ADDR, I2C_BUS

_POWER_ON = 0x01
_CONT_HIGH_RES = 0x10  # 1 lx resolution, ~120 ms per reading


class BH1750:
    def __init__(self, bus: int = I2C_BUS, address: int = BH1750_ADDR):
        from smbus2 import SMBus
        self._bus = SMBus(bus)
        self._addr = address
        self._bus.write_byte(self._addr, _POWER_ON)
        self._bus.write_byte(self._addr, _CONT_HIGH_RES)
        time.sleep(0.18)

    def lux(self) -> float:
        hi, lo = self._bus.read_i2c_block_data(self._addr, _CONT_HIGH_RES, 2)
        return ((hi << 8) | lo) / 1.2

    def close(self) -> None:
        self._bus.close()


def auto_brightness(lux: float, user_cap: int, floor: int = 8) -> int:
    """Map room light to panel brightness (%). Roughly log-shaped, 0..1000 lx."""
    import math
    level = floor + (100 - floor) * min(1.0, math.log10(1 + max(lux, 0.0)) / 3.0)
    return int(min(user_cap, level))
