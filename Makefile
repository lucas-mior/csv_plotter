PREFIX ?= /usr/local

src = main.c util.c hash.c
headers = csv_plotter.h

ldlibs = $(LDLIBS) -lmagic -lm `$( pkg-config --libs gtk4 )`

all: release

.PHONY: all clean install uninstall
.SUFFIXES:
.SUFFIXES: .c .o

clang: CC=clang
clang: CFLAGS += -Weverything -Wno-unsafe-buffer-usage -Wno-format-nonliteral
clang: clean release

CFLAGS += -std=c99 -D_DEFAULT_SOURCE
CFLAGS += -Wall -Wextra
CFLAGS += `$( pkg-config --cflags gtk4 )`

release: CFLAGS += -O2 -flto
release: csv_plotter

debug: CFLAGS += -g
debug: CFLAGS += -Dcsv_plotter_DEBUG -fsanitize=undefined
debug: CFLAGS += -Wno-format-zero-length
debug: clean csv_plotter

csv_plotter: $(src) $(headers) Makefile
	-ctags --kinds-C=+l *.h *.c
	-vtags.sed tags > .tags.vim
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(src) $(ldlibs)

install: all
	install -Dm755 csv_plotter   ${DESTDIR}${PREFIX}/bin/csv_plotter
	install -Dm644 LICENSE       ${DESTDIR}${PREFIX}/share/licenses/${pkgname}/LICENSE
uninstall:
	rm -f ${DESTDIR}${PREFIX}/bin/csv_plotter
	rm -f ${DESTDIR}${PREFIX}/share/licenses/${pkgname}/LICENSE

clean:
	rm -f csv_plotter
