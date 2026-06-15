#!/bin/sh

# Default PREFIX to /usr/local if not set in the environment
PREFIX="${PREFIX:-/usr/local}"

# Allow DESTDIR to be passed via environment, default to empty
DESTDIR="${DESTDIR:-}"

case "$1" in
    install)
        # The dependency check for csv_plotter.py is handled implicitly; 
        # 'install' will fail if the file doesn't exist.
        install -Dm755 csv_plotter.py "${DESTDIR}${PREFIX}/bin/csv_plotter.py"
        chmod +x "${DESTDIR}${PREFIX}/bin/csv_plotter.py"
        ;;
    uninstall)
        rm -f "${DESTDIR}${PREFIX}/bin/csv_plotter.py"
        ;;
    *)
        echo "Usage: $0 {install|uninstall}"
        exit 1
        ;;
esac
