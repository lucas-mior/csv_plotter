PREFIX ?= /usr/local

install: csv_plotter.py
	install -Dm755 csv_plotter.py ${DESTDIR}${PREFIX}/bin/csv_plotter.py
	chmod +x ${DESTDIR}${PREFIX}/bin/csv_plotter.py

uninstall:
	rm -f ${DESTDIR}${PREFIX}/bin/csv_plotter.py
