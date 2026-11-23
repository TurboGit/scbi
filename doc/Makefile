
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

all: $(PDF)

force:

version: force
	echo '\\providecommand{\\version}{'$(CORE_VER)'}' > version.tex

#  %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) version scbi-logo.pdf
	latexmk -pdf -interaction=nonstopmode $(TEX)

#  The logo (the SVG is the source) for the title page
scbi-logo.pdf: scbi-logo.svg
	inkscape --export-type=pdf --export-filename=$@ $<

clean:
	latexmk -C
