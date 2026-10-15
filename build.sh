#!/bin/sh

# Default PREFIX to /usr/local if not set in the environment
PREFIX="${PREFIX:-/usr/local}"

# Allow DESTDIR to be passed via environment, default to empty
DESTDIR="${DESTDIR:-}"

target="${1:-install}"

case "$target" in
    install)
        # The dependency check for csv_plotter.py is handled implicitly; 
        # 'install' will fail if the file doesn't exist.
        set -x
        install -Dm755 csv_plotter.py "${DESTDIR}${PREFIX}/bin/csv_plotter.py"
        install -Dm644 csv_plotter_units.py "${DESTDIR}${PREFIX}/bin/csv_plotter_units.py"
        install -Dm644 csv_plotter_fft.py "${DESTDIR}${PREFIX}/bin/csv_plotter_fft.py"
        set +x
        ;;
    uninstall)
        rm -f "${DESTDIR}${PREFIX}/bin/csv_plotter.py"
        rm -f "${DESTDIR}${PREFIX}/bin/csv_plotter_units.py"
        rm -f "${DESTDIR}${PREFIX}/bin/csv_plotter_fft.py"
        ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        exit 1
        ;;
esac
