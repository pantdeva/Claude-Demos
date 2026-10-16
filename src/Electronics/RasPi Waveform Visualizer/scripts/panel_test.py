#!/usr/bin/env python3
"""Bring-up test for the panel, the level shifters and the controls.

Run from the project folder:
    sudo ~/.venvs/visualizer/bin/python scripts/panel_test.py            # real panel
    python scripts/panel_test.py --simulate                              # PNG preview
    sudo ~/.venvs/visualizer/bin/python scripts/panel_test.py --controls # + knob/buttons/BH1750

Patterns (each a few seconds, looped):
  1. solid red / green / blue / white -> checks R1/G1/B1 and R2/G2/B2 lines
  2. row walk                          -> checks address lines A..E (each row once)
  3. column walk                       -> checks CLK/LAT and column order (flip_x)
  4. gradient bars                     -> checks colour depth / gamma
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from visualizer.hub75 import open_panel  # noqa: E402
from visualizer.pins import PANEL_HEIGHT as H, PANEL_WIDTH as W  # noqa: E402


def solid(rgb):
    f = np.zeros((H, W, 3), np.uint8)
    f[:] = rgb
    return f


def row_walk():
    for y in range(H):
        f = np.zeros((H, W, 3), np.uint8)
        f[y, :] = (255, 255, 255)
        yield f, 0.08


def col_walk():
    for x in range(W):
        f = np.zeros((H, W, 3), np.uint8)
        f[:, x] = (0, 255, 0)
        f[:, 0] = (255, 0, 0)  # column 0 always red: should be on the left
        yield f, 0.03


def gradient():
    f = np.zeros((H, W, 3), np.uint8)
    ramp = np.linspace(0, 255, W).astype(np.uint8)
    band = H // 4
    f[0:band, :, 0] = ramp
    f[band:2 * band, :, 1] = ramp
    f[2 * band:3 * band, :, 2] = ramp
    f[3 * band:, :, :] = ramp[:, None]
    return f


def patterns():
    for rgb in [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]:
        yield solid(rgb), 1.5
    yield from row_walk()
    yield from col_walk()
    yield gradient(), 3.0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simulate", action="store_true", help="write panel_preview.png instead")
    ap.add_argument("--brightness", type=int, default=40)
    ap.add_argument("--planes", type=int, default=6, help="bit-planes per colour (1-8)")
    ap.add_argument("--clkdiv", type=float, default=8.0, help="raise if you see noise/ghosting")
    ap.add_argument("--base-on", type=int, default=40, help="LSB on-time in PIO cycles")
    ap.add_argument("--flip-x", action="store_true", help="mirror columns")
    ap.add_argument("--controls", action="store_true", help="also test encoder, buttons, BH1750")
    args = ap.parse_args()

    panel = open_panel(simulate=args.simulate, planes=args.planes, clkdiv=args.clkdiv,
                       base_on=args.base_on, flip_x=args.flip_x, brightness=args.brightness)

    controls = sensor = None
    if args.controls:
        from visualizer.controls import Controls
        from visualizer.light_sensor import BH1750, auto_brightness
        controls = Controls()
        controls.state.brightness_cap = args.brightness
        try:
            sensor = BH1750()
        except OSError as e:
            print(f"BH1750 not found on I2C ({e}); continuing without auto-brightness")

    print(f"Panel: {type(panel).__name__}. Ctrl+C to stop.")
    last = ""
    try:
        while True:
            for frame, hold in patterns():
                if controls:
                    s = controls.state
                    level = s.brightness_cap
                    lux = None
                    if sensor and s.auto_brightness:
                        lux = sensor.lux()
                        level = auto_brightness(lux, s.brightness_cap)
                    panel.brightness = level
                    line = (f"mood={s.mood:<9} mode={s.mode:<9} lyrics={s.lyrics_enabled!s:<5} "
                            f"auto={s.auto_brightness!s:<5} brightness={level:3d}%"
                            + (f" lux={lux:6.1f}" if lux is not None else ""))
                    if line != last:
                        print(line)
                        last = line
                panel.show(frame)
                time.sleep(hold)
    except KeyboardInterrupt:
        pass
    finally:
        panel.close()
        if controls:
            controls.close()
        if sensor:
            sensor.close()


if __name__ == "__main__":
    main()
