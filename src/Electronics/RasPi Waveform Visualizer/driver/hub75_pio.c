/*
 * hub75_pio.c - HUB75 driver for Raspberry Pi 5 using the RP1 PIO block.
 *
 * How it works
 * ------------
 * The panel is 1/24 scan: row address r (0..23) lights row r (top half, via
 * R1/G1/B1) and row r+24 (bottom half, via R2/G2/B2) at the same time.
 * Colour depth uses Binary Code Modulation (BCM): each row is sent once per
 * bit-plane, and bit-plane p is lit for (base_on << p) PIO cycles.
 *
 * The CPU encodes each frame into a stream of 32-bit words. For every
 * (row, plane) block the stream holds:
 *     word 0          : number of pixels - 1           -> PIO X register
 *     words 1..W/2    : two 16-bit pixels per word     -> GPIO4..14
 *                       bits 0..5  = R1 G1 B1 R2 G2 B2
 *                       bits 6..10 = row address A..E
 *     last word       : on-time in PIO cycles - 1      -> PIO Y register
 *
 * A 7-instruction PIO program clocks the pixels out, latches the row, then
 * holds OE low for the on-time. The refresh thread re-sends the whole frame
 * stream continuously; new frames are swapped in between transfers.
 *
 * Pin map (BCM numbers) - keep in sync with visualizer/pins.py:
 *   GPIO4  R1   GPIO5  G1   GPIO6  B1   GPIO7  R2   GPIO8  G2   GPIO9  B2
 *   GPIO10 A    GPIO11 B    GPIO12 C    GPIO13 D    GPIO14 E
 *   GPIO15 CLK  GPIO16 LAT  GPIO17 OE (active low)
 * All 14 signals pass through two 74HCT245 buffers (3.3 V -> 5 V).
 *
 * Status: written for raspberrypi/utils piolib. Not yet bench-tested on a
 * panel; verify timing with a logic analyser before long runs.
 */
#define _GNU_SOURCE
#include "hub75_pio.h"

#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "piolib.h"

#define PIN_DATA_BASE   4   /* GPIO4..GPIO14: 6 colour bits + 5 address bits */
#define PIN_DATA_COUNT  11
#define PIN_SIDE_BASE   15  /* GPIO15 CLK, GPIO16 LAT, GPIO17 OE */
#define PIN_SIDE_COUNT  3
#define PIN_OE          17
#define NUM_BUFFERS     3

/*
 * PIO program, hand-assembled. Side-set uses 3 pins, no "opt" bit:
 *   side bit0 = CLK, bit1 = LAT, bit2 = OE (1 = panel dark).
 *
 *   0: out x, 32      side 0b100   ; X = pixels-1, panel dark
 *   1: out pins, 11   side 0b100   ; colour + address bits, CLK low
 *   2: out null, 5    side 0b101   ; discard padding, CLK high
 *   3: jmp x--, 1     side 0b100   ; next pixel
 *   4: out y, 32      side 0b110   ; Y = on-time, LAT high
 *   5: nop            side 0b100   ; LAT low
 *   6: jmp y--, 6     side 0b000   ; OE low: row lit for Y+1 cycles
 *   (wrap 6 -> 0)
 *
 * Loaded at offset 0 so the absolute jump targets stay valid.
 */
static const uint16_t hub75_instructions[] = {
    0x7020, 0x700B, 0x7465, 0x1041, 0x7840, 0xB042, 0x0086,
};

static const pio_program_t hub75_program = {
    .instructions = hub75_instructions,
    .length = 7,
    .origin = 0,
};

struct hub75 {
    PIO pio;
    int sm;
    int width, height, rows, planes, base_on, flip_x;
    size_t words;
    uint32_t *buf[NUM_BUFFERS];
    int front;   /* newest complete frame */
    int in_use;  /* frame the refresh thread is sending */
    pthread_mutex_t lock;
    pthread_t thread;
    atomic_int running;
    atomic_int brightness;
    uint8_t gamma[256];
    uint8_t *last_rgb;
};

static void encode(hub75_t *h, const uint8_t *rgb, uint32_t *out)
{
    const int bright = atomic_load(&h->brightness);
    size_t i = 0;

    for (int r = 0; r < h->rows; r++) {
        for (int p = 0; p < h->planes; p++) {
            out[i++] = (uint32_t)(h->width - 1);

            for (int x = 0; x < h->width; x += 2) {
                uint32_t word = 0;
                for (int k = 0; k < 2; k++) {
                    int col = h->flip_x ? (h->width - 1 - (x + k)) : (x + k);
                    const uint8_t *t = rgb + ((size_t)r * h->width + col) * 3;
                    const uint8_t *b = rgb + ((size_t)(r + h->rows) * h->width + col) * 3;
                    uint32_t px =
                        (uint32_t)((h->gamma[t[0]] >> p) & 1) << 0 |
                        (uint32_t)((h->gamma[t[1]] >> p) & 1) << 1 |
                        (uint32_t)((h->gamma[t[2]] >> p) & 1) << 2 |
                        (uint32_t)((h->gamma[b[0]] >> p) & 1) << 3 |
                        (uint32_t)((h->gamma[b[1]] >> p) & 1) << 4 |
                        (uint32_t)((h->gamma[b[2]] >> p) & 1) << 5 |
                        (uint32_t)(r & 0x1F) << 6;
                    word |= px << (16 * k);
                }
                out[i++] = word;
            }

            uint32_t on = ((uint32_t)h->base_on * (uint32_t)bright / 100u) << p;
            out[i++] = on ? on - 1 : 0;
        }
    }
}

static void *refresh_thread(void *arg)
{
    hub75_t *h = arg;
    const size_t bytes = h->words * sizeof(uint32_t);

    while (atomic_load(&h->running)) {
        pthread_mutex_lock(&h->lock);
        h->in_use = h->front;
        uint32_t *b = h->buf[h->in_use];
        pthread_mutex_unlock(&h->lock);

        if (pio_sm_xfer_data(h->pio, h->sm, PIO_DIR_TO_SM, bytes, b) < 0) {
            perror("hub75: pio_sm_xfer_data");
            break;
        }
    }
    return NULL;
}

static void publish(hub75_t *h, const uint8_t *rgb)
{
    int idx;
    pthread_mutex_lock(&h->lock);
    for (idx = 0; idx < NUM_BUFFERS; idx++)
        if (idx != h->front && idx != h->in_use)
            break;
    pthread_mutex_unlock(&h->lock);

    encode(h, rgb, h->buf[idx]);

    pthread_mutex_lock(&h->lock);
    h->front = idx;
    pthread_mutex_unlock(&h->lock);
}

hub75_t *hub75_open(int width, int height, int planes, float clkdiv,
                    int base_on, int flip_x)
{
    if (width <= 0 || width % 2 || height <= 0 || height % 2 ||
        height / 2 > 32 || planes < 1 || planes > 8 || base_on < 1) {
        fprintf(stderr, "hub75: invalid geometry or settings\n");
        return NULL;
    }

    hub75_t *h = calloc(1, sizeof(*h));
    if (!h)
        return NULL;

    h->width = width;
    h->height = height;
    h->rows = height / 2;
    h->planes = planes;
    h->base_on = base_on;
    h->flip_x = flip_x;
    h->words = (size_t)h->rows * planes * (2 + width / 2);
    atomic_init(&h->brightness, 60);
    pthread_mutex_init(&h->lock, NULL);

    const float maxv = (float)((1 << planes) - 1);
    for (int v = 0; v < 256; v++)
        h->gamma[v] = (uint8_t)lroundf(powf(v / 255.0f, 2.2f) * maxv);

    h->last_rgb = calloc((size_t)width * height, 3);
    for (int i = 0; i < NUM_BUFFERS; i++) {
        h->buf[i] = calloc(h->words, sizeof(uint32_t));
        if (!h->buf[i] || !h->last_rgb)
            goto fail_mem;
        encode(h, h->last_rgb, h->buf[i]);
    }

    h->pio = pio_open(0);
    if (PIO_IS_ERR(h->pio)) {
        fprintf(stderr, "hub75: cannot open /dev/pio0 (kernel/firmware too old, or permissions)\n");
        goto fail_mem;
    }

    h->sm = pio_claim_unused_sm(h->pio, false);
    if (h->sm < 0) {
        fprintf(stderr, "hub75: no free PIO state machine\n");
        goto fail_pio;
    }

    if (pio_sm_config_xfer(h->pio, h->sm, PIO_DIR_TO_SM,
                           h->words * sizeof(uint32_t), 1) < 0) {
        fprintf(stderr, "hub75: pio_sm_config_xfer failed\n");
        goto fail_pio;
    }

    if (!pio_can_add_program_at_offset(h->pio, &hub75_program, 0)) {
        fprintf(stderr, "hub75: PIO instruction memory at offset 0 is busy\n");
        goto fail_pio;
    }
    /* piolib's pio_add_program_at_offset() returns void; on success the
     * program sits exactly at the offset we asked for. */
    pio_add_program_at_offset(h->pio, &hub75_program, 0);
    const uint offset = 0;

    const int first = PIN_DATA_BASE;
    const int count = PIN_DATA_COUNT + PIN_SIDE_COUNT;
    for (int pin = first; pin < first + count; pin++)
        pio_gpio_init(h->pio, pin);

    /* Keep the panel dark (OE high) before the state machine starts. */
    pio_sm_set_pins_with_mask(h->pio, h->sm, 1u << PIN_OE, 1u << PIN_OE);
    pio_sm_set_consecutive_pindirs(h->pio, h->sm, first, count, true);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset + 0, offset + 6);
    sm_config_set_out_pins(&c, PIN_DATA_BASE, PIN_DATA_COUNT);
    sm_config_set_sideset_pins(&c, PIN_SIDE_BASE);
    sm_config_set_sideset(&c, PIN_SIDE_COUNT, false, false);
    sm_config_set_out_shift(&c, true, true, 32); /* shift right, autopull 32 */
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    sm_config_set_clkdiv(&c, clkdiv);
    pio_sm_init(h->pio, h->sm, offset, &c);
    pio_sm_set_enabled(h->pio, h->sm, true);

    atomic_init(&h->running, 1);
    if (pthread_create(&h->thread, NULL, refresh_thread, h) != 0) {
        fprintf(stderr, "hub75: cannot start refresh thread\n");
        pio_sm_set_enabled(h->pio, h->sm, false);
        goto fail_pio;
    }
    return h;

fail_pio:
    pio_close(h->pio);
fail_mem:
    for (int i = 0; i < NUM_BUFFERS; i++)
        free(h->buf[i]);
    free(h->last_rgb);
    free(h);
    return NULL;
}

int hub75_set_frame(hub75_t *h, const uint8_t *rgb, int len)
{
    if (!h || !rgb || len != h->width * h->height * 3)
        return -1;
    memcpy(h->last_rgb, rgb, (size_t)len);
    publish(h, h->last_rgb);
    return 0;
}

void hub75_set_brightness(hub75_t *h, int percent)
{
    if (!h)
        return;
    if (percent < 0) percent = 0;
    if (percent > 100) percent = 100;
    atomic_store(&h->brightness, percent);
    publish(h, h->last_rgb);
}

void hub75_close(hub75_t *h)
{
    if (!h)
        return;

    /* Show black for one more refresh, then stop. */
    memset(h->last_rgb, 0, (size_t)h->width * h->height * 3);
    publish(h, h->last_rgb);

    atomic_store(&h->running, 0);
    pthread_join(h->thread, NULL);

    pio_sm_set_enabled(h->pio, h->sm, false);
    pio_sm_set_pins_with_mask(h->pio, h->sm, 1u << PIN_OE, 1u << PIN_OE);
    pio_sm_unclaim(h->pio, h->sm);
    pio_close(h->pio);

    for (int i = 0; i < NUM_BUFFERS; i++)
        free(h->buf[i]);
    free(h->last_rgb);
    pthread_mutex_destroy(&h->lock);
    free(h);
}
