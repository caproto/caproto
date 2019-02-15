#!/bin/bash

echo "Setting up local caproto development environment..."

git submodule update --init

if [ ! -z "$AGENT_HOMEDIRECTORY" ]; then
    # Running on azure
    source azure_env.sh
elif [ ! -z "$TRAVIS_BUILD_DIR" -a -d "${TRAVIS_BUILD_DIR}/.ci/ci-scripts" ]; then
    # If the CI scripts are available, use the potentially updated version
    pushd ${TRAVIS_BUILD_DIR}/.ci
    echo "Calling sub-module dev env script"
    source setup_local_dev_env.sh
    popd
    # Reset the build directory for this repository
    export TRAVIS_BUILD_DIR=${PWD}
else
    # mock Travis
    export TRAVIS_BUILD_DIR=${PWD}
    export EPICS_HOST_ARCH=linux-x86_64
    export EPICS_CA_ADDR_LIST=127.255.255.255
    export EPICS_CA_AUTO_ADDR_LIST=NO
    export EPICS_CA_MAX_ARRAY_BYTES=10000000

    source ${TRAVIS_BUILD_DIR}/.ci/epics-config.sh
fi
