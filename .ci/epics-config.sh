export SUPPORT=$HOME/.cache/support
export IOCS=$HOME/.cache/iocs
export EPICS_BASE=$SUPPORT/epics-base
export RELEASE_PATH=$SUPPORT/RELEASE
export EPICS_HOST_ARCH=linux-x86_64

export PYEPICS_IOC="$IOCS/pyepics-test-ioc"
export PYEPICS_IOC_SOCK="pyepics-test-ioc"
export MOTORSIM_IOC="$IOCS/motorsim"
export MOTORSIM_IOC_SOCK="motorsim-ioc"

install -d $SUPPORT
install -d $IOCS

if [ ! -f "$RELEASE_PATH" ]; then
    cat << EOF > $RELEASE_PATH
# SNCSEQ=$SUPPORT/seq
BUSY=$SUPPORT/busy
ASYN=$SUPPORT/asyn
CALC=$SUPPORT/calc
MOTOR=$SUPPORT/motor
EPICS_BASE=$SUPPORT/epics-base
EOF
    echo "Created release file: ${RELEASE_PATH}"
    cat $RELEASE_PATH
fi

EPICS_BIN_PATH="$EPICS_BASE/bin/${EPICS_HOST_ARCH}"

if [[ ":$PATH:" != *":${EPICS_BIN_PATH}:"* ]]; then
    export PATH="${EPICS_BIN_PATH}:${PATH}"
    echo "${EPICS_BIN_PATH} added to path"
fi

export PYEPICS_LIBCA=$EPICS_BASE/lib/${EPICS_HOST_ARCH}/libca.so
