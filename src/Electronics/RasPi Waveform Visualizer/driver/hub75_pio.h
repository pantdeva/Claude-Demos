/*
 * hub75_pio.h - Minimal HUB75 LED matrix driver for Raspberry Pi 5 (RP1 PIO).
 *
 * Drives a Waveshare RGB-Matrix-P2.5-96x48-F (HUB75, 1/24 scan) through two
 * 74HCT245 level shifters. The pin map is fixed in hub75_pio.c and must match
 * visualizer/pins.py and the README wiring tables.
 */
#ifndef HUB75_PIO_H
#define HUB75_PIO_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct hub75 hub75_t;

/*
 * Open the panel and start the background refresh thread.
 *   width, height : panel size in pixels (96, 48). Height/2 is the scan (24).
 *   planes        : colour depth in bit-planes per channel (1..8, default 6).
 *   clkdiv        : PIO clock divider. Higher = slower, safer HUB75 clock.
 *   base_on       : on-time of the least significant bit-plane, in PIO cycles.
 *   flip_x        : 1 to mirror columns if the image appears reversed.
 * Returns NULL on failure (message printed to stderr).
 */
hub75_t *hub75_open(int width, int height, int planes, float clkdiv,
                    int base_on, int flip_x);

/* Show a frame: RGB888, row-major, width*height*3 bytes. Returns 0 on success. */
int hub75_set_frame(hub75_t *h, const uint8_t *rgb, int len);

/* Global brightness 0..100 %. Re-encodes the last frame. */
void hub75_set_brightness(hub75_t *h, int percent);

/* Blank the panel, stop refresh and release the PIO state machine. */
void hub75_close(hub75_t *h);

#ifdef __cplusplus
}
#endif

#endif /* HUB75_PIO_H */
