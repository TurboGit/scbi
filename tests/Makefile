
.SILENT: test clean

force:

test:
	./run

clean: force
	./clean

#  Python port: run each driver with the Python driver, refuse regressions
#  against python-pass.txt
ratchet: force
	./ratchet

#  The same with the YAML versions of the test plug-ins, against
#  python-yaml-pass.txt
ratchet-yaml: force
	./ratchet --format=yaml
