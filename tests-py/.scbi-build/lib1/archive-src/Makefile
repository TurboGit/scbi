
all: lib1.a lib1.so main

lib1.a: lib1.o
	ar cr liblib1.a lib1.o

lib1.so: lib1.o
	gcc -shared -o liblib1.so lib1.o

lib1.o: lib1.c
lib1.c: lib1.h
main.c: lib1.h
main.o: main.c

main: main.o
	gcc -o main main.o -llib1
