
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

all: $(PDF)

force:

version: force
	echo '\\providecommand{\\version}{'$(CORE_VER)'}' > version.tex

#  %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) version
	-latex $(TEX)
	-bibtex $(NAM)
	-makeindex $(NAM)
	-latex $(TEX)
	pdflatex $(TEX)

clean:
	rm -f *.bbl *.blg *.log *.out *.toc *.aux $(PDF)
