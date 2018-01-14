#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

[ -z "$EPICS_BASE" ] && echo "EPICS_BASE unset" && exit 1;
[ -z "$SUPPORT" ] && echo "SUPPORT unset" && exit 1;


# # sequencer
# if [ ! -e "$SUPPORT/seq/built" ]; then
#     echo "Build sequencer"
#     install -d $SUPPORT/seq
#     curl -L "http://www-csr.bessy.de/control/SoftDist/sequencer/releases/seq-${SEQ}.tar.gz" | tar -C $SUPPORT/seq -xvz --strip-components=1
#     cp $RELEASE_PATH $SUPPORT/seq/configure/RELEASE
#     make -C $SUPPORT/seq
#     touch $SUPPORT/seq/built
# else
#     echo "Using cached seq"
# fi


# asyn
if [ ! -e "$SUPPORT/asyn/built" ]; then
    echo "Build asyn"
    install -d $SUPPORT/asyn
    curl -L "https://github.com/epics-modules/asyn/archive/R${ASYN}.tar.gz" | tar -C $SUPPORT/asyn -xvz --strip-components=1
    cp $RELEASE_PATH $SUPPORT/asyn/configure/RELEASE
    make -C "$SUPPORT/asyn" -j2
    touch $SUPPORT/asyn/built
else
    echo "Using cached asyn"
fi


# busy
if [ ! -e "$SUPPORT/busy/built" ]; then
    echo "Build busy"
    install -d $SUPPORT/busy
    curl -L "https://github.com/epics-modules/busy/archive/R${BUSY}.tar.gz" | tar -C $SUPPORT/busy -xvz --strip-components=1
    cp $RELEASE_PATH $SUPPORT/busy/configure/RELEASE
    make -C $SUPPORT/busy
    touch $SUPPORT/busy/built
else
    echo "Using cached busy"
fi


# calc
if [ ! -e "$SUPPORT/calc/built" ]; then
    echo "Build calc"
    install -d $SUPPORT/calc
    git clone https://github.com/epics-modules/calc ${SUPPORT}/calc
    ( cd ${SUPPORT}/calc && git checkout ${CALC} )
    cp $RELEASE_PATH $SUPPORT/calc/configure/RELEASE
    make -C "$SUPPORT/calc" -j2
    touch $SUPPORT/calc/built
else
    echo "Using cached calc"
fi


# motor
if [ ! -e "$SUPPORT/motor/built" ]; then
    echo "Build motor"
    install -d $SUPPORT/motor
    curl -L "https://github.com/epics-modules/motor/archive/R${MOTOR}.tar.gz" | tar -C $SUPPORT/motor -xvz --strip-components=1
    cp $RELEASE_PATH $SUPPORT/motor/configure/RELEASE
    if [ "$MOTOR" = "6-9" ]; then
        # not building ipac support
        sed -ie s/^.*Hytec.*$// $SUPPORT/motor/motorApp/Makefile
    fi
    # aerotech requires sequencer
    sed -ie s/^.*Aerotech.*$// $SUPPORT/motor/motorApp/Makefile
	if [[ "$BASE" =~ ^R3\.16.* ]]; then
        # pretty much everything fails under 3.16 -- replace the Makefile
        cat > "$SUPPORT/motor/motorApp/Makefile" <<'EOF'
TOP = ..
include $(TOP)/configure/CONFIG
DIRS += MotorSrc SoftMotorSrc MotorSimSrc Db
SoftMotorSrc_DEPEND_DIRS = MotorSrc
MotorSimSrc_DEPEND_DIRS = MotorSrc
include $(TOP)/configure/RULES_DIRS
EOF
    fi
    make -C "$SUPPORT/motor" -j2
    touch $SUPPORT/motor/built
else
    echo "Using cached motor"
fi
