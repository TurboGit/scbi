
.SILENT: test

SCRDIR=$(HOME)/.config/scbi

all:
	mkdir -p $(HOME)/bin
	cp scbi $(HOME)/bin
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*~ scripts.d/*~
	cp scripts.d/* $(SCRDIR)

test:
	make -C tests test

test-clean:
	make -C tests clean
