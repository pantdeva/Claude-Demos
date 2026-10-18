# Builds libhub75.so, the HUB75 PIO driver loaded by visualizer/hub75.py.
#
# Requires piolib from https://github.com/raspberrypi/utils (scripts/install.sh
# builds and installs it). If piolib was installed somewhere else, override:
#   make PIOLIB_INC=/path/to/piolib/include PIOLIB_LIB=/path/to/lib

PIOLIB_PREFIX ?= /usr/local
PIOLIB_INC    ?= $(PIOLIB_PREFIX)/include
PIOLIB_LIB    ?= $(PIOLIB_PREFIX)/lib

CC      ?= gcc
CFLAGS  ?= -O2
CFLAGS  += -Wall -Wextra -fPIC -std=gnu11 -I$(PIOLIB_INC) -I$(PIOLIB_INC)/piolib
LDLIBS  += -L$(PIOLIB_LIB) -Wl,-rpath,$(PIOLIB_LIB) -lpio -lpthread -lm

.PHONY: all clean

all: libhub75.so

libhub75.so: hub75_pio.c hub75_pio.h
	$(CC) $(CFLAGS) -shared -o $@ hub75_pio.c $(LDLIBS)

clean:
	rm -f libhub75.so
