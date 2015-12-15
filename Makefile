
all:
	cp scbi $(HOME)/bin
	mkdir -p $(HOME)/.scbi.d
	rm -f $(HOME)/.scbi.d/*~
	cp scripts.d/*  $(HOME)/.scbi.d
