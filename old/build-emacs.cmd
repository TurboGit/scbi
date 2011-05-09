@echo off

echo Be sure to call setgcc before
echo pause

set PATH=c:\opt\GNATPRO\5.03a\bin;c:\cygwin\bin
set C_INCLUDE_PATH=c:\opt\GNATPRO\5.03a\pentium-mingw32msv\include

cd emacs-*
cd nt
call configure --with-gcc
mkdir \opt\emacs-new

make USER_LDFLAGS="-s" INSTALL_DIR=c:/opt/emacs-new

make USER_LDFLAGS="-s" INSTALL_DIR=c:/opt/emacs-new install
