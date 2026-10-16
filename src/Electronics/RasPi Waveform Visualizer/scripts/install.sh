#!/usr/bin/env bash
# One-time setup on Raspberry Pi OS 64-bit (Bookworm or newer) on a Raspberry Pi 5.
# Run from the project folder:  bash scripts/install.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-$HOME/.venvs/visualizer}"

echo "==> System packages"
sudo apt update
sudo apt install -y git build-essential cmake pkg-config python3-venv python3-dev \
    i2c-tools libportaudio2

echo "==> Firmware/kernel up to date (needed for /dev/pio0)"
sudo apt full-upgrade -y

echo "==> Interfaces: I2C on; SPI and serial console off (their pins drive the panel)"
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 1
sudo raspi-config nonint do_serial_cons 1
sudo raspi-config nonint do_serial_hw 1

echo "==> piolib (RP1 PIO userspace library)"
if [ ! -d "$HOME/rpi-utils" ]; then
    git clone --depth 1 https://github.com/raspberrypi/utils "$HOME/rpi-utils"
fi
cmake -S "$HOME/rpi-utils/piolib" -B "$HOME/rpi-utils/build-piolib" -DCMAKE_BUILD_TYPE=Release
cmake --build "$HOME/rpi-utils/build-piolib" -j4
sudo cmake --install "$HOME/rpi-utils/build-piolib"
sudo ldconfig

echo "==> Let the gpio group use PIO without sudo"
echo 'SUBSYSTEM=="*-pio", GROUP="gpio", MODE="0660"' | sudo tee /etc/udev/rules.d/99-pio.rules >/dev/null
sudo usermod -aG gpio,i2c "$USER"
sudo udevadm control --reload-rules && sudo udevadm trigger

echo "==> Build the HUB75 driver"
make -C "$PROJECT_DIR/driver"

echo "==> Python virtual environment (PEP 668)"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

echo
echo "Done. Reboot once (interface and group changes), then run:"
echo "  $VENV/bin/python scripts/panel_test.py --brightness 30"
