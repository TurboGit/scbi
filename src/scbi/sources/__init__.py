"""Sources of a module: VCS checkouts and archives (port of
handle-sources, scripts.d/4_scm and the archive functions of
scripts.d/5_tools).

Layout (each VCS and each download protocol in its own module, selected
through a registry, so that adding one is one module and one entry):

- data.py: the vcs/archive hook data (get-vcs-data, get-archive-data);
- vcs/: the VCS implementations (vcs/registry.py);
- archive/: the download protocols and the extraction (archive/registry.py);
- buildid.py: build and source identifiers.
"""
