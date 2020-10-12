
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

VER=$(shell git describe)

all: $(PDF)

force:

version: force
	echo '\\providecommand{\\version}{'$(VER)'}' > version.tex

# %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) version
	-latex $(TEX)
	-bibtex $(NAM)
	-makeindex $(NAM)
	-latex $(TEX)
	pdflatex $(TEX)

clean:
	rm -f *.bbl *.blg *.log *.out *.toc *.aux $(PDF)
