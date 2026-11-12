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
