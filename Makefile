
SCRDIR=$(HOME)/.config/scbi

all:
	cp scbi $(HOME)/bin
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*
	cp scripts.d/*  $(SCRDIR)
