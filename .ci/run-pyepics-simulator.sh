#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh
export PYEPICS_LIBCA=$HOME/.cache/support/epics-base/lib/${EPICS_HOST_ARCH}/libca.so

echo "Running pyepics simulator program..."
python ${PYEPICS_IOC}/simulator.py &
sleep 1
