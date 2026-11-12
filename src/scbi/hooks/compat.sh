#  SCBI - functions of the driver available to the runtime and the hooks.
#
#  Copied from the Bash driver (scbi) where the runtime (scripts.d/[0-9]*)
#  and plug-ins expect them; loaded first in every hook shell by the
#  Python driver. tests/unit/test_hooks_exec.py checks that they are
#  identical to the ones of the Bash driver.

declare -A FLATDIR=()
FTDIR=1

function check-tool()
{
    if [[ -z "$(command -v $1 2> /dev/null)" ]]; then
        return 1
    fi
    return 0
}

function check-tools()
{
    local res=0

    while [[ -n $1 ]]; do
        check-tool $1
        res=$(($res + $?))
        shift
    done
    return $res
}

function check-tools-abort()
{
    local TOOLS="$*"

    local MISSING=""

    for T in $TOOLS; do
	check-tool $T || MISSING+=" $T"
    done

    [[ -n $MISSING ]] &&
	{
            echo Required tools${MISSING} missing, please install
            exit 1
	}

    return 0
}

function read-content()
{
    local -n VAR=$1
    VAR=""
    [[ -f $2 ]] &&
        read VAR < $2
}

function append-content()
{
    local -n VAR=$1
    read LV < $2
    VAR+=$LV
}

function get-target-dir()
{
    local -n _REF=$1
    local MODULE=$2
    local VARIANT=$3
    local FILE=$4

    local VAL=""
    local TDF=$SCBI_BDIR/$MODULE/$SCBI_TARGET-$VARIANT

    if [[ $DO_FLAT == yes ]]; then
        local KEY=$MODULE-$VARIANT
        VAL=${FLATDIR[$KEY]}

        if [[ -n $VAL ]]; then
            true
        elif [[ -h $TDF ]]; then
            VAL=$(realpath $TDF)
            FLATDIR+=( [$KEY]="${VAL}" )
        elif [[ -f $TDF$SCBI_LNK ]]; then
            get-ln VAL $TDF
            VAL=$(realpath $SCBI_BDIR/$MODULE/$VAL)
            FLATDIR+=( [$KEY]="${VAL}" )
        else
            while [[ -d $SCBI_BDIR/$FTDIR ]]; do
                (( FTDIR++ ))
            done
            VAL=$SCBI_BDIR/$FTDIR
            mkdir -p $SCBI_BDIR/$MODULE
            module-purge-tvdir $TDF
            rm -fr $TDF
            ln -s ../$FTDIR $TDF
            FLATDIR+=( [$KEY]="${VAL}" )
        fi

    else
        VAL=$TDF

        [[ -h $TDF ]] &&
            rm -fr $(realpath $TDF) $TDF
        [[ -f $TDF$SCBI_LNK ]] &&
            {
                local RDIR=""
                get-ln RDIR $TDF
                rm -fr $(realpath $SCBI_BDIR/$MODULE/$RDIR) $TDF$SCBI_LNK
            }
    fi

    _REF=${VAL}${FILE:+/$FILE}
}

function clean-up()
{
    rm -f $SCBI_HANDLED
    rm -f $SCBI_LINE_SEP
}

#  Environment of a module (handle-module): run by the Python driver in a
#  shell until the dependency walker is ported (Step 6).

function handle-module-env()
{
    local FORMODULE=$1
    local MODREF=$2
    local ENV=$3

    #  Get module information

    local module_info=()
    get-module-ref module_info $MODREF $FORMODULE

    local module=${module_info[0]}
    local variant=${module_info[1]}
    local ref=${module_info[3]}

    [[ "$ref" == "skip" ]] && return 0

    if [[ -n $SCBI_ENV_MODULE ]]; then
        {
            echo
            echo "# $MODREF"
        } >> $SCBI_ENV_MODULE
    fi

    local TVDIR=""
    get-target-dir TVDIR $module $variant

    local BUILDDIR=build
    [[ $SCBI_ISOOT == false ]] && BUILDDIR=src

    SCBI_MODULES_DIR["$module"]="$TVDIR/install"
    SCBI_MODULES_DIR["${module}@src"]="$TVDIR/src"
    SCBI_MODULES_DIR["${module}@build"]="$TVDIR/$BUILDDIR"

    plugin-call-env-hooks $FORMODULE $MODREF $ENV
}

function handle-env-callback()
{
    local FORMODULE=$1
    local MODREF=$2
    local LEVEL=$3
    local DEPENDS_KIND=$4
    local IS_EXT=$5
    local IS_META=$6
    local IS_AGGREGATED=$7

    #  Nothing to do for aggregated module as the env has already been
    #  set as part of the aggregate module.

    [[ $IS_AGGREGATED == true ]] && return

    #  Only the environment of the dependencies and not self. The env
    #  hook of a module is only used for clients and not for the module
    #  itself.

    [[ $LEVEL -ge 1 ]] ||
        [[ $DEPENDS_KIND == tests ]] ||
        is-meta-module $FORMODULE > /dev/null &&
        {
            handle-module-env $FORMODULE $MODREF env
        }
}

function handle-env()
{
    local FORMODULE=$1
    local MODREF=$2

    for-all-modules-depends-with-meta handle-env-callback $MODREF
}

function handle-build-depends-env()
{
    local FORMODULE=$1
    local MODREF=$2

    for-all-modules-build-depends-with-meta handle-env-callback $MODREF
}

function handle-tests-depends-env()
{
    local FORMODULE=$1
    local MODREF=$2

    for-all-modules-tests-depends-with-meta handle-env-callback $MODREF
}

function check-handled()
{
    local KEY=$1

    grep "^$KEY" $SCBI_HANDLED &> /dev/null

    if [[ $? = 1 ]]; then
        echo "$KEY" >> $SCBI_HANDLED
        return 1
    else
        return 0
    fi
}

function record-dref()
{
    local MODULE=$1
    local VARIANT=$2
    local FILE=$3

    [[ -f $SCBI_BDIR/$MODULE/build-id-$VARIANT ]] &&
        {
            read-content BIV $SCBI_BDIR/$MODULE/build-id-$VARIANT
            echo "$BIV $MODULE" >> $FILE
        }
    true
}

#  Sources of a module and running of a step (I/O, logs): run by the
#  Python driver in a shell until ported.

function handle-sources()
{
    local FORMODULE=$1
    local MODREF=$2

    #  Get module information

    local module_info=()
    get-module-ref module_info $MODREF $FORMODULE

    local module=${module_info[0]}
    local variant=${module_info[1]}
    local kind=${module_info[2]}
    local ref=${module_info[3]}

    [[ "$variant" = "native" ]] &&
        {
            echo -n "native-$ref" > source-id-$variant
            echo "$module none native revision $ref" > source-ref
            return 0;
        }

    rm -f source-ref

    #  Check if a given archive exists even if a standard branch ref has
    #  been provided. This is an optimization to used a local archive
    #  instead of a repository branch.

    if [[ $kind == BRANCH ]] && [[ "$ARCHIVE_CACHE" == "yes" ]]; then
        check-archive-exists $module $variant $ref && kind=VERSION
    fi

    local HASSRC=yes

    #  If building from archive, extract it now

    if [[ $kind == VERSION ]]; then
        local tar=( $(get-archive-data $module $variant $ref) )
        local nv=${#tar[*]}

        if [[ $nv == 0 ]]; then
            echo "error: $module-archive function not defined, cannot get archive"
            exit 1
        fi

        if [[ $nv != 6 ]] && [[ $nv != 7 ]]; then
            local V=${tar[0]}
            if [[ $V == default ]]; then
                V=""
            else
                V+="-"
            fi
            local nv=$(( $nv - 1 ))
            echo "error: $module-${V}archive function returned $nv values, 5 or 6 expected"
            exit 1
        fi

        tarsrc=${tar[5]}

        [[ ${tarsrc^^} == NONE ]] && HASSRC=no

        [[ -d archive-src ]] &&
            {
                get-ln archivefile archive
                local ABN=$(basename $(realpath $archivefile))
                [[ ${tarsrc} != $ABN ]] &&
                    rm -fr archive-sha1$SCBI_LNK archive$SCBI_LNK archive-src
            }

        #  We need to extract the archive if the version does not match
        #  the one currently extracted.

        if [[ -f source-id-$variant ]]; then
            read-content SIV source-id-$variant
            if [[ "$SIV" != "archive-$ref" ]] ||
                   [[ $HASSRC == no ]];
            then
                rm -fr archive-src
            fi
        fi

        if [[ $HASSRC == yes ]]; then
            if [[ $DO_UPDATE = yes ]] || [[ ! -d archive-src ]] || [[ ! -e archive$SCBI_LNK ]]; then
                V=${tar[0]#default}
                ilog $module get sources from archive ${V:+[$V]}

                get-archive $module $variant $ref 2>>$log | tee -a $log
                res=${PIPESTATUS[0]}

                if [[ $res != 0 ]]; then
                    #  In case of error display log from get-archive
                    grep FAILED $log
                    ilog $module cannot get/find/extract archive sources
                    exit 1
                fi
            fi

            echo -n "archive-$ref" > source-id-$variant
            cp source-id-$variant source-id

            #  Compute and store the version id of the sources. This includes the
            #  tar sha1 if present to ensure a tar with the same name but different
            #  content will trigger a build.

            local archive_sha1="NONE"
            [[ -e archive-sha1$SCBI_LNK ]] &&
                {
                    get-ln sha1file archive-sha1
                    read-content archive_sha1 $sha1file
                    archive_sha1=${archive_sha1// */}
                }
            echo "$module archive $ref sha-1 ${archive_sha1// */}" \
                 > source-ref

            get-build-id $SCBI_PREFIX $SCBI_TARGET \
                         $FORMODULE $MODREF archive-$ref$archive_sha1 \
                         > build-id-$variant

            #  We set the link for the source so that no module will have to
            #  do it.

            ln -s archive-src src
        fi
    else
        #  Get sources from repository

        local vcs=( $(get-vcs-data $module $variant) )

        local nv=${#vcs[*]}

        if [[ $nv != 0 ]] && [[ $nv != 5 ]] && [[ $nv != 6 ]]; then
            local V=${vcs[0]}
            if [[ $V == default ]]; then
                V=""
            else
                V+="-"
            fi
            local nv=$(( $nv - 1 ))
            echo "error: $module-${V}vcs function returned $nv values, 4 or 5 expected"
            exit 1
        fi

        local VCS_NAME=${vcs[3]}
        local VCS_URL=${vcs[4]}

        if [[ $nv > 0 ]] && [[ "${VCS_NAME^^}" != "NONE" ]]; then
            REPO=$(basename $VCS_URL .git)

            if [[ $kind = DEV ]]; then
                local SCBI_VCS_REPO=""
                get-vcs-user-co-dir SCBI_VCS_REPO $module $VCS_NAME

                [[ $SCBI_VCS_REPO == NONE ]] &&
                    {
                        elog $MODULE unsupported VCS $VCS_NAME
                        exit 1
                    }

                if [[ -d $SCBI_VCS_REPO/$REPO ]]; then
                    ln -s $SCBI_VCS_REPO/$REPO vcs

                    #  Compute and store the version id of the sources

                    local VCSDIR=""
                    get-ln VCSDIR vcs

                    local rdev=""
                    [[ $ref == "dev" ]] &&
                        rdev="-$(get-vcs-commit-id true $VCS_NAME $VCSDIR)"

                    echo -n "$ref$rdev" > source-id-$variant
                    cp source-id-$variant source-id

                    vcs-build-id $SCBI_PREFIX $SCBI_TARGET \
                                 $FORMODULE $MODREF $VCSDIR \
                                 > build-id-$variant

                else
                    ilog $module cannot find local dev repository:
                    ilog $module $SCBI_VCS_REPO/$REPO
                    exit 1
                fi

            else
                if [[ $DO_TEST != "yes-only" ]]; then
                    if [[ -f source-id ]]; then
                        read-content SID source-id
                        if [[ "$SID" != "vcs-$ref" ]]; then
                            # a different version is needed
                            DO_UPDATE=yes
                        fi
                    else
                        DO_UPDATE=yes
                    fi
                fi

                if [[ $DO_UPDATE = yes ]] || [[ ! -d ../.vcs/$REPO ]]; then
                    V=${vcs[0]#default}
                    ilog $module get sources from $VCS_NAME ${V:+[$V]}

                    get-vcs $SCBI_PREFIX $SCBI_TARGET $FORMODULE $MODREF ||
                        exit 1
                else
                    ln -s ../.vcs/$REPO vcs
                fi

                echo -n "vcs-$ref" > source-id-$variant

                #  Compute and store the version id of the sources +
                #  compiler. That is when the compiler is changed we
                #  want to rebuild the software.

                local VCSDIR=""
                get-ln VCSDIR vcs

                vcs-build-id $SCBI_PREFIX $SCBI_TARGET \
                             $FORMODULE $MODREF $VCSDIR \
                             > build-id-$variant
            fi

            if [[ ! -e src$SCBI_LNK ]]; then
                #  Setting source reference, note that for Subversion this
                #  need to properly set the link to the directory in the vcs.
                #  This action is done by svn-branch that we call here.

                case $VCS_NAME in
                    svn|subversion)
                        svn-branch "" "" $module $ref ""
                        ;;
                    *)
                        ln -s vcs src
                        ;;
                esac
            fi

            echo -n "$module " > source-ref
            get-vcs-ref $VCS_NAME $ref $(pwd)/vcs >> source-ref
            cp source-id-$variant source-id

            return 0

        else
            HASSRC=no
        fi

        #  If get-vcs is not defined then the $module-setup routine is in
        #  charge of creating/populating the src directory.
    fi

    [[ $HASSRC == no ]] &&
        {
            echo -n "none-$ref" > source-id-$variant
            cp source-id-$variant source-id
            echo $module none $variant revision $ref >> source-ref

            #  No VCS, no TAR, just rebuild the sources if present
            if [[ ! -d src ]]; then
                ilog $module "no sources (vcs or tar)"

                get-build-id $SCBI_PREFIX $SCBI_TARGET \
                             $FORMODULE $MODREF "$variant" \
                             > build-id-$variant
            else
                get-build-id $SCBI_PREFIX $SCBI_TARGET \
                             $FORMODULE $MODREF "$EPOCHSECONDS" \
                             > build-id-$variant
            fi
        } || true
}

function module-wrapper()
{
    local PREFIX=$1
    local MODULE=$2
    local VARIANT=$3
    local STEP=$4

    local dvariant=""

    #  set variant display if not part of step and not default

    if [[ ${STEP/$VARIANT/} == $STEP && "$VARIANT" != "default" ]]; then
        dvariant=" [${VARIANT//./ }]"
    fi

    if [[ $STEP = "build" ]] && [[ -n $BUILD_SCBI_TARGET ]]; then
        mstep=build-$BUILD_SCBI_TARGET
    else
        mstep=$STEP
    fi

    #  global logs
    local log=$SCBI_LOGS/$TODAY/$SCBI_TARGET-$MODULE-$VARIANT-$mstep.log

    local TVDIR=""
    get-target-dir TVDIR $MODULE $VARIANT

    #  local log for last module command
    local mlog=$TVDIR/logs/$mstep.log
    local clog=$TVDIR/logs/$mstep.cmd

    fn-exists $MODULE-cached
    local IS_CACHED=$?

    if [[ $IS_CACHED == 0 ]] && [[ $mstep != tests ]]; then
        ilog $MODULE $mstep$dvariant cached
    else
        ilog $MODULE $mstep$dvariant starting
    fi

    (
        cd $SCBI_BDIR/$MODULE >> $log 2>&1

        #  Go to build directory, if not out of tree build go to src

        local BUILDDIR=build
        [[ $SCBI_ISOOT == false ]] && BUILDDIR=src

        if [[ "$STEP" =~ (pre-|post-)*(setup|wrapup)$ ]]; then
            cd $SCBI_BDIR/$MODULE
        elif [[ -d $TVDIR/$BUILDDIR ]]; then
            cd $TVDIR/$BUILDDIR
        else
            #  a native module has no sources for example
            cd $SCBI_BDIR/$MODULE
        fi

        #  Record run command

        show-command $MODULE $MODULE-$mstep \
                     $PREFIX $SCBI_TARGET $VARIANT 2&> $clog

        #  Call module step

        local res=0

        local IS_TESTS=no
        local TEST_OPTS=

        if [[ "$STEP" =~ "tests" ]]; then
            IS_TESTS=yes
            TESTS_OPTS="$SCBI_TESTS_OPTIONS"
        fi

        [[ $IS_TESTS == no ]] && [[ $IS_CACHED == 0 ]] && return 0

        if [[ $SCBI_DLOG = yes ]] || [[ "$IS_TESTS" = "yes" ]]; then
            $MODULE-$mstep $PREFIX $SCBI_TARGET $VARIANT "$TESTS_OPTS" 2>&1 \
                | tee -a $log | tee $mlog
            #  We want the status of the first command and not the tee ones
            res=${PIPESTATUS[0]}
        else
            {
                PS4="_TRACE: "
                set -o xtrace
                $MODULE-$mstep $PREFIX $SCBI_TARGET $VARIANT
                res=$?
                set +o xtrace
                return $res
            } 2>&1 | tee $mlog &>> $log
            res=${PIPESTATUS[0]}
        fi

        #  Check for errors

        if [[ $res -ne 0 ]]; then
            if [[ $SCBI_DLOG = on-failure ]] && [[ "$STEP" != "tests" ]]; then
                tail -100 $mlog | grep -v "^_[_]*TRACE: "
            fi
            elog $MODULE $mstep failed with error $res

            local RDIR=$TVDIR/logs

            case $STEP in
                *config|*build|*install|*cross-config|*cross-build|*cross-install)
                    elog $MODULE to reproduce:
                    elog $MODULE bash $RDIR/$mstep.cmd
                    elog $MODULE use bash -x option for debug
                    ;;
            esac

            return $res
        else
            ilog $MODULE $mstep$dvariant completed
            return 0
        fi
    )
    return $?
}

function _internal_module-variant-wrapper()
{
    local PREFIX=$1
    local MODULE=$2
    local VARIANT=$3
    local FCT=$4

    [[ -z $FCT ]] && return

    #  Now check that the body is not empty (default variant)
    local BODY=$(declare -f $FCT | tail --lines=-3)
    local BODY=$(echo $BODY)
    local res=0

    if [[ "$BODY" != "{ true }" ]]; then
        module-wrapper $PREFIX $MODULE \
                       $VARIANT ${FCT#"${MODULE}-"} || exit 1
        res=$?
    fi
    return $res
}

function module-variant-wrapper()
{
    local PREFIX=$1
    local MODULE=$2
    local VARIANT=$3
    local STEP=$4

    local FCT=""
    get-hook FCT $MODULE $VARIANT $STEP

    if [[ -n $FCT ]]; then
        _internal_module-variant-wrapper $PREFIX $MODULE $VARIANT $FCT
    fi
}
