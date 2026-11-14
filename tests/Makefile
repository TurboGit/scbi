
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
