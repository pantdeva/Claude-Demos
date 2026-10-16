"""Single source of truth for every GPIO used by the visualizer (BCM numbering).

The HUB75 pins are also hard-coded in driver/hub75_pio.c, because the PIO
program needs them as one contiguous block (GPIO4..GPIO17). Change both
together, and update README.md and docs/wiring.svg.
"""

# --- HUB75 panel, via two 74HCT245 level shifters (U1, U2) -----------------
# signal: (BCM GPIO, physical header pin, buffer chip, HUB75 IDC pin)
HUB75 = {
    "R1":  (4, 7, "U1", 1),
    "G1":  (5, 29, "U1", 2),
    "B1":  (6, 31, "U1", 3),
    "R2":  (7, 26, "U1", 5),
    "G2":  (8, 24, "U1", 6),
    "B2":  (9, 21, "U1", 7),
    "CLK": (15, 10, "U1", 13),
    "LAT": (16, 36, "U1", 14),
    "A":   (10, 19, "U2", 9),
    "B":   (11, 23, "U2", 10),
    "C":   (12, 32, "U2", 11),
    "D":   (13, 33, "U2", 12),
    "E":   (14, 8, "U2", 8),
    "OE":  (17, 11, "U2", 15),   # active low; 10 kOhm pull-up to 3.3 V
}

# --- User controls (gpiozero, internal pull-ups) ---------------------------
ENCODER_A = 22     # KY-040 CLK, physical pin 15
ENCODER_B = 23     # KY-040 DT,  physical pin 16
ENCODER_SW = 24    # KY-040 SW,  physical pin 18  (press = toggle lyrics)
BUTTON_MOOD = 25   # physical pin 22  (next mood)
BUTTON_BRIGHT = 26 # physical pin 37  (brightness step / auto)
BUTTON_MODE = 27   # physical pin 13  (visual mode)

# --- Ambient light sensor (I2C bus 1) --------------------------------------
I2C_BUS = 1        # SDA = GPIO2 (pin 3), SCL = GPIO3 (pin 5)
BH1750_ADDR = 0x23 # ADDR pin tied to GND

# --- Left free on purpose ----------------------------------------------------
# GPIO18-21 (pins 12, 35, 38, 40): I2S, for an optional I2S MEMS microphone.
# GPIO0/1 (pins 27, 28): HAT ID EEPROM, never use.
# Audio input is a USB audio interface, which uses no GPIO.

PANEL_WIDTH = 96
PANEL_HEIGHT = 48
