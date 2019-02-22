
.SILENT: test

SCRDIR=$(HOME)/.config/scbi

all:
	cp scbi $(HOME)/bin
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*
	cp scripts.d/*  $(SCRDIR)

test:
	make -C tests test

test-clean:
	make -C tests clean
