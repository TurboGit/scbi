# scbi

Setup Configure Build Install - Tool to build from sources with local developers checkout support


# A simple tutorial to build Little-CMS

Little-CMS is an Open Source Color Management System project
(http://www.littlecms.com/). The source code is on GitHub, the URL is:

   https://github.com/mm2/Little-CMS.git


## Install scbi

Checkout this repository and do:

      $ make


## Check scbi status

By default the scbi build directories can be displayed with --stat option (output after the usage information):

      $ scbi --stat

      stats
      -----
      build dir             : $HOME/dev/builds
      install prefix        : $HOME/dev/builds/install
      tar dir               : $HOME/dev/builds/.tar
      patches dir           : $HOME/dev/builds/.patches
      user's Git repository : $HOME/dev/repositories/git
      user's SVN repository : $HOME/dev/repositories/svn
      e-mail notification   : no


# lcms module

0. The scbi build module name will be lcms

   Open your favorite editor to create lcms file. This file must be placed into
   $HOME/.config/scbi for it to be found by scbi driver.

   All (bash) functions in this file will be prefixed by "lcms-".

1. Defining the VCS

   In this function we define the protocol and the location of the repository.

      ```
      function lcms-vcs()
      {
             echo default
             echo none
             echo git
             echo http://github.com/mm2/Little-CMS
      }
      ```

2. This project is based autotools and so using configure. The build
   directory can be separate from the sources. This is an out-of-tree
   build, let's declare this:

      ```
      function lcms-out-of-tree()
      {
             echo true
      }
      ```

   Note that this routine is optional, and when not defined it means
   that we are building into the source directory.

3. Then we need to configure the project:

      ```
      function lcms-config()
      {
          local PREFIX=$1
          local TARGET=$2

          ../src/configure --prefix=$PREFIX
      }
      ```

   Note that the "config" (but also build and install functions below)
   are called in the proper location. That is, it is never needed to
   change directory. So above we are in the build directory and the
   source directory is always on the same level and named src. This is
   true whether we are building out-of-tree or not. Above src the a
   separate directory where the sources are to be found.

   Note also that hook functions are passed PREFIX and TARGET. The
   PREFIX is not the final install location. It is the location of the
   module install directory.

4. Now it is time to build the project:

      ```
      function lcms-build()
      {
          local PREFIX=$1
          local TARGET=$2

          make -j4
      }
      ```

   Again, we are placed into the right directory, so we just need to call make.

5. Let's install the project:

      ```
      function lcms-install()
      {
          local PREFIX=$1
          local TARGET=$2

          make install
      }
      ```

   Note, that this will install into the module install directory.

6. This is optional, but if we want to have the final installation
   done in a specific location (default in /usr for Little-CMS) we can
   specify it with the prefix function:

      ```
      function lcms-prefix()
      {
          echo /opt/lcms
      }
      ```

   Note that this is equivalent to calling scbi with --prefix parameter:

      `$ scbi --prefix=/opt/lcms lcms`

   If the final install prefix is not writable by user, a sudo
   password will be asked.


## Building lcms

And that's all is needed to build this project. Now to build it:

      $ scbi lcms
      2019/12/03 13:16:24 : Building lcms [default] (master)
      2019/12/03 13:16:24 : native x86_64-linux-gnu
      2019/12/03 13:16:24 : steps : setup config build install wrapup
      2019/12/03 13:16:24 : get sources from git
      2019/12/03 13:16:33 : config starting
      2019/12/03 13:16:39 : config completed
      2019/12/03 13:16:39 : build starting
      2019/12/03 13:16:45 : build completed
      2019/12/03 13:16:45 : install starting
      2019/12/03 13:16:46 : install completed
      2019/12/03 13:16:46 : copy install into ../opt/lcms
      2019/12/03 13:16:46 : End building lcms [default] (master)

If you call it again, nothing will happen as scbi will detect that the
sources have not changed:

      $ scbi lcms
      2019/12/03 13:18:01 : Building lcms [default] (master)
      2019/12/03 13:18:01 : native x86_64-linux-gnu
      2019/12/03 13:18:01 : steps : setup config build install wrapup
      2019/12/03 13:18:01 : no build needed, versions match
      2019/12/03 13:18:01 : copy install into ../opt/lcms
      2019/12/03 13:18:01 : End building lcms [default] (master)


## A release variant

Now, we'd want to create a fast release version of the code. The
default is to compile with "-g -O2". We want to add a release variant
to build with just "-O3" at configuration step:

      function lcms-release-config()
      {
          local PREFIX=$1
          local TARGET=$2

          CFLAGS="-O3" ../src/configure --prefix=$PREFIX
      }

And then build the release version:

      $ scbi lcms/release
      2019/12/03 13:18:23 : Building lcms [release] (master)
      2019/12/03 13:18:23 : native x86_64-linux-gnu
      2019/12/03 13:18:23 : steps : setup config build install wrapup
      2019/12/03 13:18:24 : release-config starting
      2019/12/03 13:18:28 : release-config completed
      2019/12/03 13:18:28 : build [release] starting
      2019/12/03 13:18:35 : build [release] completed
      2019/12/03 13:18:35 : install [release] starting
      2019/12/03 13:18:35 : install [release] completed
      2019/12/03 13:18:35 : copy install into ../opt/lcms
      2019/12/03 13:18:35 : End building lcms [release] (master)

Note that the variant release-config is properly called above.


## Building v2.9

Up to now we have been building on the master branch. Whatever code is
there, each time we call scbi we can update the source from upstream
repository and rebuild if some modifications are found:

      $ scbi -u lcms/release
      2019/12/03 13:21:30 : Building lcms [release] (master)
      2019/12/03 13:21:30 : native x86_64-linux-gnu
      2019/12/03 13:21:30 : steps : setup config build install wrapup
      2019/12/03 13:21:30 : get sources from git
      2019/12/03 13:21:32 : no build needed, versions match
      2019/12/03 13:21:32 : copy install into ../opt/lcms
      2019/12/03 13:21:32 : End building lcms [release] (master)

There was no modification, so nothing built. But for our project we
want a stable version properly identified and tagged. Latest version
of Little-CMS is 2.9, tagged as lcms2.9, to build it it is as simple as:

      $ scbi -u lcms/release:lcms2.9
      2019/12/03 13:22:59 : Building lcms [release] (lcms2.9)
      2019/12/03 13:22:59 : native x86_64-linux-gnu
      2019/12/03 13:22:59 : steps : setup config build install wrapup
      2019/12/03 13:22:59 : get sources from git
      2019/12/03 13:23:01 : release-config starting
      2019/12/03 13:23:05 : release-config completed
      2019/12/03 13:23:05 : build [release] starting
      2019/12/03 13:23:12 : build [release] completed
      2019/12/03 13:23:12 : install [release] starting
      2019/12/03 13:23:12 : install [release] completed
      2019/12/03 13:23:12 : copy install into ../opt/lcms
      2019/12/03 13:23:13 : End building lcms [release] (lcms2.9)


## Developing lcms

We take part of the project and want to fix a bug on this project. So
we want to get a local checkout.

      $ cd $HOME
      $ mkdir dev
      $ cd dev
      $ git clone http://github.com/mm2/Little-CMS

First step is to configure scbi driver to point it to our local Git
checkouts. The default as listed above is:

      user's Git repository : $HOME/dev/repositories/git

The default configuration file can be found in:

      $ vi $HOME/.config/scbi/.env

So we need to set GIT_REPO to point to $HOME/dev.

      GIT_REPO=$HOME/dev

We can now start hacking the project from our local checkout:

      $ cd $HOME/dev/Little-CMS
      $ vi ...

And to test this new developer's version, we need to pass :dev as
version to scbi:

      $ scbi lcms:dev
      2019/12/03 13:24:33 : Building lcms [default] (dev)
      2019/12/03 13:24:33 : native x86_64-linux-gnu
      2019/12/03 13:24:33 : steps : setup config build install wrapup
      2019/12/03 13:24:33 : config starting
      2019/12/03 13:24:38 : config completed
      2019/12/03 13:24:38 : build starting
      2019/12/03 13:24:45 : build completed
      2019/12/03 13:24:45 : install starting
      2019/12/03 13:24:45 : install completed
      2019/12/03 13:24:45 : copy install into ../opt/lcms
      2019/12/03 13:24:45 : End building lcms [default] (dev)

Building a dev version also supports the variant:

      $ scbi lcms/release:dev
