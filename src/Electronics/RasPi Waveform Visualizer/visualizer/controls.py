"""Physical controls: KY-040 rotary encoder and three push buttons.

Wiring (BCM GPIO / physical pin), all with the Pi's internal pull-ups:
    Encoder CLK -> GPIO22 / 15     Encoder DT -> GPIO23 / 16
    Encoder SW  -> GPIO24 / 18     Encoder +  -> 3.3 V / 17 (NOT 5 V)
    Mood button       GPIO25 / 22 -> GND
    Brightness button GPIO26 / 37 -> GND
    Mode button       GPIO27 / 13 -> GND

Uses gpiozero with the lgpio pin factory, which works on the Pi 5
(RPi.GPIO does not).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from . import pins

MOODS = ["Auto", "Calm", "Happy", "Energetic", "Romantic", "Dark", "Dreamy"]
MODES = ["spectrum", "waves", "particles", "lyrics"]
BRIGHTNESS_STEPS = [20, 40, 60, 80, 100]


@dataclass
class ControlState:
    mood_index: int = 0
    mode_index: int = 0
    brightness_cap: int = 60
    auto_brightness: bool = True
    lyrics_enabled: bool = True
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def mood(self) -> str:
        return MOODS[self.mood_index]

    @property
    def mode(self) -> str:
        return MODES[self.mode_index]


class Controls:
    """Turn the knob or press Mood to change mood; Mode cycles visuals;
    Brightness steps the cap (the last step switches auto-brightness on/off)."""

    def __init__(self, state: ControlState | None = None):
        from gpiozero import Button, Device, RotaryEncoder
        from gpiozero.pins.lgpio import LGPIOFactory

        Device.pin_factory = LGPIOFactory()
        self.state = state or ControlState()

        self._enc = RotaryEncoder(pins.ENCODER_A, pins.ENCODER_B, max_steps=0)
        self._enc.when_rotated_clockwise = lambda: self._step_mood(+1)
        self._enc.when_rotated_counter_clockwise = lambda: self._step_mood(-1)

        self._sw = Button(pins.ENCODER_SW, pull_up=True, bounce_time=0.05)
        self._sw.when_pressed = self._toggle_lyrics

        self._mood = Button(pins.BUTTON_MOOD, pull_up=True, bounce_time=0.05)
        self._mood.when_pressed = lambda: self._step_mood(+1)

        self._bright = Button(pins.BUTTON_BRIGHT, pull_up=True, bounce_time=0.05)
        self._bright.when_pressed = self._step_brightness

        self._mode = Button(pins.BUTTON_MODE, pull_up=True, bounce_time=0.05)
        self._mode.when_pressed = self._step_mode

    def _step_mood(self, d: int) -> None:
        with self.state.lock:
            self.state.mood_index = (self.state.mood_index + d) % len(MOODS)

    def _step_mode(self) -> None:
        with self.state.lock:
            self.state.mode_index = (self.state.mode_index + 1) % len(MODES)

    def _toggle_lyrics(self) -> None:
        with self.state.lock:
            self.state.lyrics_enabled = not self.state.lyrics_enabled

    def _step_brightness(self) -> None:
        with self.state.lock:
            s = self.state
            if s.auto_brightness:
                s.auto_brightness = False
                s.brightness_cap = BRIGHTNESS_STEPS[0]
            elif s.brightness_cap == BRIGHTNESS_STEPS[-1]:
                s.auto_brightness = True
            else:
                i = BRIGHTNESS_STEPS.index(s.brightness_cap)
                s.brightness_cap = BRIGHTNESS_STEPS[i + 1]

    def close(self) -> None:
        for dev in (self._enc, self._sw, self._mood, self._bright, self._mode):
            dev.close()
