
.SILENT: test

SCRDIR=$(HOME)/.config/scbi
VER=$(shell git describe)

install: all

all:
	mkdir -p $(HOME)/bin
	cat scbi | sed "s/@VERSION@/$(VER)/" > $(HOME)/bin/scbi
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*~ scripts.d/*~
	cp -r scripts.d/* $(SCRDIR)

test:
	make -C tests test

test-clean:
	make -C tests clean

doc: force
	make -C doc

force:
