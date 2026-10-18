"""Live audio input from the USB audio interface (or USB mic).

Part: USB audio interface, plugged into one of the Pi 5's blue USB 3 ports.
No GPIO is used, so GPIO18-21 stay free for an optional I2S microphone.

`AudioCapture` opens the device with sounddevice (PortAudio over ALSA), keeps
the newest samples in a ring buffer, and `features()` turns the latest window
into what the renderer needs:

    bands  : N log-spaced spectrum bands (40 Hz - 16 kHz), auto-gained to 0..1
    level  : overall loudness 0..1 (RMS, auto-gained)
    onset  : 0..1 spike when a beat/hit lands (positive spectral flux)
    peak_db: raw RMS level in dBFS, useful for checking input gain

List devices with:  python -m visualizer.audio_capture --list
Live meter:         python -m visualizer.audio_capture
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 48_000
WINDOW = 2048          # FFT size: ~43 ms at 48 kHz, 23 Hz bins
NUM_BANDS = 24
F_MIN, F_MAX = 40.0, 16_000.0


@dataclass
class AudioFeatures:
    bands: np.ndarray   # shape (NUM_BANDS,), 0..1
    level: float        # 0..1
    onset: float        # 0..1
    peak_db: float      # dBFS


class AudioCapture:
    """Ring-buffered capture plus FFT feature extraction."""

    def __init__(self, device: int | str | None = None,
                 sample_rate: int = SAMPLE_RATE, num_bands: int = NUM_BANDS):
        import sounddevice as sd  # imported here so the simulator works without it

        self.sample_rate = sample_rate
        self._ring = np.zeros(WINDOW * 4, dtype=np.float32)
        self._pos = 0
        self._lock = threading.Lock()

        # Band edges: log-spaced, mapped to FFT bin indices.
        edges_hz = np.geomspace(F_MIN, F_MAX, num_bands + 1)
        bins = np.fft.rfftfreq(WINDOW, 1.0 / sample_rate)
        self._edges = np.searchsorted(bins, edges_hz)
        self._edges = np.maximum.accumulate(np.maximum(self._edges, 1))
        self._window = np.hanning(WINDOW).astype(np.float32)

        # Auto-gain: slowly decaying running maxima, so quiet and loud rooms
        # both fill the panel.
        self._band_max = np.full(num_bands, 1e-3, dtype=np.float32)
        self._level_max = 1e-3
        self._prev_mag = None
        self._flux_avg = 1e-6

        self._stream = sd.InputStream(device=device, channels=1,
                                      samplerate=sample_rate, blocksize=512,
                                      dtype="float32", callback=self._callback)
        self._stream.start()

    def _callback(self, indata, frames, _time, status):
        if status:
            pass  # overflow etc.; dropping a block is harmless for a visualizer
        x = indata[:, 0]
        with self._lock:
            n = len(x)
            end = self._pos + n
            if end <= len(self._ring):
                self._ring[self._pos:end] = x
            else:
                k = len(self._ring) - self._pos
                self._ring[self._pos:] = x[:k]
                self._ring[:n - k] = x[k:]
            self._pos = end % len(self._ring)

    def _latest(self) -> np.ndarray:
        with self._lock:
            idx = (np.arange(WINDOW) + self._pos - WINDOW) % len(self._ring)
            return self._ring[idx]

    def features(self) -> AudioFeatures:
        x = self._latest()
        rms = float(np.sqrt(np.mean(x * x)) + 1e-12)
        peak_db = 20.0 * np.log10(rms)

        mag = np.abs(np.fft.rfft(x * self._window))
        bands = np.array([mag[a:b].mean() if b > a else mag[a]
                          for a, b in zip(self._edges[:-1], self._edges[1:])],
                         dtype=np.float32)

        # Onset: positive spectral flux against its own running average.
        if self._prev_mag is None:
            self._prev_mag = mag
        flux = float(np.maximum(mag - self._prev_mag, 0.0).sum())
        self._prev_mag = mag
        self._flux_avg = 0.95 * self._flux_avg + 0.05 * flux
        onset = float(np.clip((flux / (self._flux_avg + 1e-9) - 1.3) / 2.0, 0.0, 1.0))

        # Auto-gain with slow decay (about 5 s to halve at 60 updates/s).
        self._band_max = np.maximum(self._band_max * 0.998, bands)
        self._level_max = max(self._level_max * 0.998, rms)
        bands = np.clip(bands / self._band_max, 0.0, 1.0)
        level = float(np.clip(rms / self._level_max, 0.0, 1.0))
        return AudioFeatures(bands=bands, level=level, onset=onset, peak_db=peak_db)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def _main() -> None:
    ap = argparse.ArgumentParser(description="USB audio input check")
    ap.add_argument("--list", action="store_true", help="list audio devices and exit")
    ap.add_argument("--device", help="device index or name (default: system default)")
    args = ap.parse_args()

    import sounddevice as sd
    if args.list:
        print(sd.query_devices())
        return

    dev = int(args.device) if args.device and args.device.isdigit() else args.device
    cap = AudioCapture(device=dev)
    print("Listening. Ctrl+C to stop. Aim for peaks around -12 to -6 dBFS.")
    try:
        while True:
            f = cap.features()
            bars = "".join(" ▁▂▃▄▅▆▇█"[int(v * 8)] for v in f.bands)
            hit = "●" if f.onset > 0.3 else " "
            print(f"\r{f.peak_db:6.1f} dBFS {hit} {bars}", end="", flush=True)
            time.sleep(1 / 30)
    except KeyboardInterrupt:
        print()
    finally:
        cap.close()


if __name__ == "__main__":
    _main()
