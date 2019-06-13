
NAM = scbi
TEX = $(NAM).tex
PDF = $(NAM).pdf

all: $(PDF)

force:

# %.pdf: %.tex $(DIF) $(BIB)

$(PDF): $(TEX) $(DIF) $(BIB) force
	-latex $(TEX)
	-bibtex $(NAM)
	-makeindex $(NAM)
	-latex $(TEX)
	latex $(TEX)

clean:
	rm -f *.bbl *.blg *.log *.out *.toc *.aux $(PDF)
