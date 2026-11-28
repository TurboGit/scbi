"""The binary store: the installations of the modules keyed by what they
are built from (binary key), reused instead of building.

- key.py: the binary key of a build (its components, normalized);
- relocate.py: the paths of the origin sandbox in the installed files;
- blob.py: an entry (tarball and metadata);
- stores.py: the stores (file, ...) and their list;
- flow.py: lookup, install and upload during a build.

See doc/scbi.tex, section "Binary store".
"""
