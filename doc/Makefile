
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

all: $(PDF)

force:

version: force
	echo '\\providecommand{\\version}{'$(CORE_VER)'}' > version.tex

#  %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) version
	latexmk -pdf -interaction=nonstopmode $(TEX)

clean:
	latexmk -C
