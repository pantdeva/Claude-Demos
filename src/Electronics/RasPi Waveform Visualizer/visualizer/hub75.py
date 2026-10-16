"""Python interface to the HUB75 panel.

`Hub75Panel` loads driver/libhub75.so (our RP1 PIO driver) with ctypes.
`SimulatedPanel` has the same interface and writes PNG previews, so the rest
of the project can be developed on a laptop without the panel attached.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

import numpy as np

from .pins import PANEL_HEIGHT, PANEL_WIDTH

_LIB_PATH = Path(__file__).resolve().parent.parent / "driver" / "libhub75.so"


def _as_rgb_bytes(frame, width: int, height: int) -> bytes:
    """Accept a numpy array (H, W, 3) uint8 or a PIL image; return RGB888 bytes."""
    if hasattr(frame, "convert"):  # PIL.Image
        frame = np.asarray(frame.convert("RGB"))
    arr = np.ascontiguousarray(frame, dtype=np.uint8)
    if arr.shape != (height, width, 3):
        raise ValueError(f"frame must be {height}x{width}x3, got {arr.shape}")
    return arr.tobytes()


class Hub75Panel:
    """Real panel, driven by the PIO driver. Needs root or the gpio/pio udev rule."""

    def __init__(self, width: int = PANEL_WIDTH, height: int = PANEL_HEIGHT,
                 planes: int = 6, clkdiv: float = 8.0, base_on: int = 40,
                 flip_x: bool = False, brightness: int = 60,
                 lib_path: str | os.PathLike = _LIB_PATH):
        self.width, self.height = width, height
        self._lib = ctypes.CDLL(str(lib_path))
        self._lib.hub75_open.restype = ctypes.c_void_p
        self._lib.hub75_open.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_float, ctypes.c_int, ctypes.c_int]
        self._lib.hub75_set_frame.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self._lib.hub75_set_frame.restype = ctypes.c_int
        self._lib.hub75_set_brightness.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lib.hub75_close.argtypes = [ctypes.c_void_p]

        self._h = self._lib.hub75_open(width, height, planes, clkdiv, base_on, int(flip_x))
        if not self._h:
            raise RuntimeError("hub75_open failed - see stderr (permissions, /dev/pio0, wiring)")
        self.brightness = brightness

    @property
    def brightness(self) -> int:
        return self._brightness

    @brightness.setter
    def brightness(self, percent: int) -> None:
        self._brightness = max(0, min(100, int(percent)))
        self._lib.hub75_set_brightness(self._h, self._brightness)

    def show(self, frame) -> None:
        data = _as_rgb_bytes(frame, self.width, self.height)
        if self._lib.hub75_set_frame(self._h, data, len(data)) != 0:
            raise RuntimeError("hub75_set_frame rejected the frame")

    def close(self) -> None:
        if self._h:
            self._lib.hub75_close(self._h)
            self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class SimulatedPanel:
    """Drop-in stand-in that saves every Nth frame as an enlarged PNG."""

    def __init__(self, width: int = PANEL_WIDTH, height: int = PANEL_HEIGHT,
                 out_path: str = "panel_preview.png", every: int = 30,
                 brightness: int = 60, **_ignored):
        self.width, self.height = width, height
        self.out_path, self.every = out_path, every
        self.brightness = brightness
        self._count = 0

    def show(self, frame) -> None:
        data = np.frombuffer(_as_rgb_bytes(frame, self.width, self.height), np.uint8)
        self._count += 1
        if self._count % self.every:
            return
        from PIL import Image
        img = data.reshape(self.height, self.width, 3).astype(np.float32)
        img = (img * self.brightness / 100).astype(np.uint8)
        Image.fromarray(img).resize((self.width * 8, self.height * 8),
                                    Image.NEAREST).save(self.out_path)

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_panel(simulate: bool = False, **kwargs):
    """Open the real panel, or the simulator when asked or when the driver is missing."""
    if not simulate and _LIB_PATH.exists():
        return Hub75Panel(**kwargs)
    return SimulatedPanel(**kwargs)
