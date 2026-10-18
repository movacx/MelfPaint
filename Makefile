# Instalación común para los paquetes .deb, .rpm y de Arch Linux.
#
#   make install DESTDIR=/tmp/raiz PREFIX=/usr
#   make test
#   make packages            (deb, rpm y arch en dist/)

PREFIX ?= /usr
DESTDIR ?=
PYTHON ?= /usr/bin/python3
APP_ID := io.github.movacx.MelfPaint
VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' app/version.py)

BINDIR := $(PREFIX)/bin
DATADIR := $(PREFIX)/share
APPDIR := $(DATADIR)/melfpaint

.PHONY: all install uninstall test run packages deb rpm arch clean

all:
	@echo "MelfPaint $(VERSION): use 'make install', 'make test' o 'make packages'."

install:
	install -d "$(DESTDIR)$(APPDIR)"
	cp -R app/backend app/frontend "$(DESTDIR)$(APPDIR)/"
	find "$(DESTDIR)$(APPDIR)" -name '__pycache__' -type d -prune -exec rm -rf {} +
	find "$(DESTDIR)$(APPDIR)" -type d -exec chmod 755 {} +
	find "$(DESTDIR)$(APPDIR)" -type f -exec chmod 644 {} +
	install -m644 app/main.py app/version.py "$(DESTDIR)$(APPDIR)/"
	install -d "$(DESTDIR)$(BINDIR)"
	sed -e 's|@PYTHON@|$(PYTHON)|g' -e 's|@APPDIR@|$(APPDIR)|g' packaging/common/melfpaint.in > "$(DESTDIR)$(BINDIR)/melfpaint"
	chmod 755 "$(DESTDIR)$(BINDIR)/melfpaint"
	install -Dm644 packaging/common/$(APP_ID).desktop "$(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop"
	install -Dm644 packaging/common/$(APP_ID).metainfo.xml "$(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml"
	install -Dm644 packaging/common/$(APP_ID).xml "$(DESTDIR)$(DATADIR)/mime/packages/$(APP_ID).xml"
	install -Dm644 app/frontend/Resources/app-icons/melfpaint.svg "$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg"
	install -Dm644 LICENSE "$(DESTDIR)$(DATADIR)/licenses/melfpaint/LICENSE"
	install -Dm644 README.md "$(DESTDIR)$(DATADIR)/doc/melfpaint/README.md"

uninstall:
	rm -rf "$(DESTDIR)$(APPDIR)" "$(DESTDIR)$(DATADIR)/doc/melfpaint" "$(DESTDIR)$(DATADIR)/licenses/melfpaint"
	rm -f "$(DESTDIR)$(BINDIR)/melfpaint" \
	      "$(DESTDIR)$(DATADIR)/applications/$(APP_ID).desktop" \
	      "$(DESTDIR)$(DATADIR)/metainfo/$(APP_ID).metainfo.xml" \
	      "$(DESTDIR)$(DATADIR)/mime/packages/$(APP_ID).xml" \
	      "$(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APP_ID).svg"

test:
	cd app && QT_QPA_PLATFORM=offscreen $(PYTHON) -m unittest discover -s tests -t .

run:
	cd app && $(PYTHON) main.py

packages:
	packaging/build-packages.sh all

deb rpm arch:
	packaging/build-packages.sh $@

clean:
	rm -rf build dist
	find app -name '__pycache__' -type d -prune -exec rm -rf {} +
