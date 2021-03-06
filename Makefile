
.SILENT: test

SCRDIR=$(HOME)/.config/scbi
VER=$(shell git describe)

install: all

all: clean.install
	mkdir -p $(HOME)/bin
	cat scbi | sed "s/@VERSION@/$(VER)/" > $(HOME)/bin/scbi
	chmod u+x $(HOME)/bin/scbi
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*~ $(SCRDIR)/.*~ scripts.d/*~ scripts.d/.*~
	cp -r scripts.d/* scripts.d/.[a-z]* $(SCRDIR)
	echo "CORE plugins : ${VER}" > $(SCRDIR)/.scbi_core_version.txt

	cd scripts.d; find . -type f > $(SCRDIR)/.core.plugins

clean.install:
	if [ -f $(SCRDIR)/.core.plugins ]; then            \
		cat $(SCRDIR)/.core.plugins |              \
			while read file; do                \
				rm -f $(SCRDIR)/$$file;    \
			done;                              \
		rm -f $(SCRDIR)/.core.plugins;             \
		rm -f $(SCRDIR)/.scbi_core_version.txt;    \
	fi

test:
	make -C tests test

test-clean:
	make -C tests clean

doc: force
	make -C doc

force:
