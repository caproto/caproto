#!/bin/bash

git submodule update --init

# mock Travis
export TRAVIS_BUILD_DIR=${PWD}

# If the CI scripts are available, use the potentially updated version
if [ -d "${TRAVIS_BUILD_DIR}/.ci/ci-scripts" ]; then
    pushd ${TRAVIS_BUILD_DIR}/.ci
    source setup_local_dev_env.sh
    popd
    # Reset the build directory for this repository
    export TRAVIS_BUILD_DIR=${PWD}
else
    export EPICS_HOST_ARCH=linux-x86_64
    export EPICS_CA_ADDR_LIST=127.255.255.255
    export EPICS_CA_AUTO_ADDR_LIST=NO
    export EPICS_CA_MAX_ARRAY_BYTES=10000000
    # example build matrix variables
    export BASE=R3.14.12.6
    export BUSY=1-6-1
    export SEQ=2.2.5
    export ASYN=4-31
    export CALC=R3-6-1
    export MOTOR=6-9

    source ${TRAVIS_BUILD_DIR}/.ci/epics-config.sh
fi
