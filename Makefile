######################################################################
#
#  Install the driver (Python: needs python3 and python3-yaml) and the
#  plug-ins:
#
#     $ make
#
#  Check the plug-ins:
#
#     $ make lint
#
#  Synchronize the OS packages for supported platforms:
#
#     $ make sync-os-deps
#
#  Sorting OS packages for supported platforms:
#
#     $ make sort-pkgs
#
#  Run the regression testsuite:
#
#     $ make test
#
#  Build the documentation PDF:
#
#     $ make doc
#

.SILENT: test sort-pkgs sync-os-deps lint

.PHONY: unit test vscode vscode-smoke

SHELL=/bin/bash

SCRDIR=$(HOME)/.config/scbi
INSTALL_DIR=$(HOME)/.local/bin
LIB_DIR=$(HOME)/.local/lib/scbi

#  The tools of the former Bash driver, removed from old installations
BASH_TOOLS=scbi-lint scbi-format scbi-store scbi-source-archive scbi-show scbi-shell

#  Get SHA-1 of last commit in core SCBI
CORE_SHA1=$(shell git log -1 --format="%h" -- src/scbi pyproject.toml scripts.d/.pkgs-* \
	bash_completion.d/*)
CORE_VER=$(shell git describe $(CORE_SHA1))

PLG_SHA1=$(shell git log -1 --format="%h" -- scripts.d/c-* scripts.d/patches)
PLG_VER=$(shell git describe $(PLG_SHA1))

install: all

all: clean.install
	python3 -c "import yaml" 2> /dev/null || \
		{ echo "PyYAML is needed: apt install python3-yaml (or pip install PyYAML)"; exit 1; }
	mkdir -p $(INSTALL_DIR) $(LIB_DIR) $(HOME)/.bash_completion.d/
	#  The Python driver: a copy of the package (version stamped) and a
	#  wrapper running it
	rm -fr $(LIB_DIR)/scbi
	cp -r src/scbi $(LIB_DIR)/scbi
	find $(LIB_DIR)/scbi -name __pycache__ -prune -exec rm -fr {} +
	sed -i "s/@VERSION@/$(CORE_VER)/" $(LIB_DIR)/scbi/driver.py
	printf '%s\n' '#!/bin/bash' \
		'SCBI_ARGV0="$$0" PYTHONPATH=$(LIB_DIR)$${PYTHONPATH:+:$$PYTHONPATH} exec python3 -m scbi "$$@"' \
		> $(INSTALL_DIR)/scbi
	chmod u+x $(INSTALL_DIR)/scbi
	#  Remove old installation if any (the Bash driver tools)
	rm -f $(HOME)/bin/scbi
	rm -f $(HOME)/bin/scbi-lint
	for t in $(BASH_TOOLS); do rm -f $(INSTALL_DIR)/$$t; done
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
				echo $(SCRDIR)/$$file;     \
			done | xargs -n 25 rm -f ;         \
		rm -f $(SCRDIR)/.core.plugins;             \
		rm -f $(SCRDIR)/.scbi_core_version.txt;    \
	fi
	rm -f $(HOME)/.bash_completion.d/scbi

lint:
	PYTHONPATH=src python3 -m scbi lint --error scripts.d/c-*.yaml
	echo No problem detected

#  Unit tests of the driver
PYTEST=python3 -m pytest

#  Regression testsuite (tests/drivers/testNNN.py, see tests/harness.py),
#  in parallel when pytest-xdist is installed; T="test001 test092" runs
#  some drivers. JUnit XML report in tests/junit.xml.
XDIST := $(shell python3 -c 'import xdist' 2>/dev/null && echo "-n auto")
DRIVERS = $(if $(T),$(foreach d,$(T),tests/drivers/$(d).py),tests/drivers)

test:
	$(PYTEST) -q -p no:cacheprovider $(XDIST) --junitxml=tests/junit.xml $(DRIVERS)

test-clean:
	rm -f tests/junit.xml

unit:
	$(PYTEST) -q tests/unit

doc: force
	make CORE_VER=$(CORE_VER) -C doc

#  The VSCode extension (editors/vscode, needs Node.js): its tests, then
#  the package scbi-<version>.vsix; vscode-smoke loads it in VSCode
#  (the code command, xvfb-run without a display)
vscode:
	cd editors/vscode && npm ci --no-audit --no-fund && npm test && npm run package

vscode-smoke:
	cd editors/vscode && npx tsc -p . && \
	  $(if $(DISPLAY),,xvfb-run -a) node out/test/smoke/run.js

#  All .pkgs files but debian one
ALLPKGS := $(wildcard scripts.d/.pkgs-*)
PKGS    := $(filter-out scripts.d/.pkgs-deb, $(ALLPKGS))

#  Sort list of package entries in .pkgs-* files
sort-pkgs:
	for pkgs in $(ALLPKGS); do \
		head -2 $$pkgs > tmp; \
		tail +3 $$pkgs | sort >> tmp; \
		mv tmp $$pkgs; \
	done

#  Sync deb pkgs from all other distribs
to-deb:
	for pkgs in $(PKGS); do \
	   diff <( cat $$pkgs | grep -v '^#' | cut -d' ' -f1 | sort ) \
	        <( cat scripts.d/.pkgs-deb | grep -v '^#' | cut -d' ' -f1 | sort ) \
		| grep '^<' | cut -d' ' -f2 > tmp; \
	   cat tmp >> scripts.d/.pkgs-deb; \
	done

#  Sync all distribs pkgs from deb one
from-deb: to-deb
	for pkgs in $(PKGS); do \
	   diff <( cat scripts.d/.pkgs-deb | grep -v '^#' | cut -d' ' -f1 | sort ) \
	        <( cat $$pkgs | grep -v '^#' | cut -d' ' -f1 | sort ) \
		| grep '^<' | cut -d' ' -f2 > tmp; \
	   cat tmp >> $$pkgs; \
	done

sync-os-deps: from-deb sort-pkgs

.NOTPARALLEL: sync-os-deps

force:
