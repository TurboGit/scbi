
.SILENT: test

SCRDIR=$(HOME)/.config/scbi

#  Get SHA-1 of last commit in core SCBI
CORE_SHA1=$(shell git log -1 --format="%h" -- scbi scripts.d/[0-9]* \
	scripts.d/_os_*)
CORE_VER=$(shell git describe $(CORE_SHA1))

PLG_SHA1=$(shell git log -1 --format="%h" -- scripts.d/c-* scripts.d/patches)
PLG_VER=$(shell git describe $(PLG_SHA1))

install: all

all: clean.install
	mkdir -p $(HOME)/bin $(HOME)/.bash_completion.d/
	cat scbi | sed "s/@VERSION@/$(CORE_VER)/" > $(HOME)/bin/scbi
	chmod u+x $(HOME)/bin/scbi
	mkdir -p $(SCRDIR)
	rm -f $(SCRDIR)/*~ $(SCRDIR)/.*~ scripts.d/*~ scripts.d/.*~
	cp -r scripts.d/* scripts.d/.[a-z]* $(SCRDIR)
	echo "CORE plugins : ${PLG_VER}" > $(SCRDIR)/.scbi_core_version.txt

	cd scripts.d; find . -type f > $(SCRDIR)/.core.plugins
	cp bash_completion.d/scbi $(HOME)/.bash_completion.d/

clean.install:
	if [ -f $(SCRDIR)/.core.plugins ]; then            \
		cat $(SCRDIR)/.core.plugins |              \
			while read file; do                \
				rm -f $(SCRDIR)/$$file;    \
			done;                              \
		rm -f $(SCRDIR)/.core.plugins;             \
		rm -f $(SCRDIR)/.scbi_core_version.txt;    \
	fi
	rm -f $(HOME)/.bash_completion.d/scbi

test:
	make -C tests test

test-clean:
	make -C tests clean

doc: force
	make CORE_VER=$(CORE_VER) -C doc

force:
