
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

all: $(PDF)

version:
	sed -n 's/SCBI_VERSION=\(.*\)/\\providecommand{\\version}{\1}/p' \
	../scbi > version.tex

# %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) version
	-latex $(TEX)
	-bibtex $(NAM)
	-makeindex $(NAM)
	-latex $(TEX)
	pdflatex $(TEX)

clean:
	rm -f *.bbl *.blg *.log *.out *.toc *.aux $(PDF)
