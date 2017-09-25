#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

# -- pyepics test ioc --

if [ ! -e "${PYEPICS_IOC}/built" ]; then
    echo "Build pyepics test IOC"
    install -d $PYEPICS_IOC
    git clone --depth 10 --branch master https://github.com/pyepics/testioc.git ${PYEPICS_IOC}
    cp ${RELEASE_PATH} ${PYEPICS_IOC}/configure/RELEASE
    # no sscan support for now
    sed -ie "s/^.*sscan.*$//" ${PYEPICS_IOC}/testiocApp/src/Makefile
    # # it's late and sequencer+calc is giving issues...
    # sed -ie "s/^SNCSEQ.*$//" ${PYEPICS_IOC}/configure/RELEASE
    make -C ${PYEPICS_IOC}
    touch ${PYEPICS_IOC}/built
else
    echo "Using cached pyepics test IOC"
fi

# -- motorsim ioc --

if [ ! -e "${MOTORSIM_IOC}/built" ]; then
    echo "Build motorsim IOC"
    install -d $MOTORSIM_IOC
    git clone --depth 10 --branch homebrew-epics https://github.com/klauer/motorsim.git ${MOTORSIM_IOC}
    cp ${RELEASE_PATH} ${MOTORSIM_IOC}/configure/RELEASE
    # no autosave support for now
    sed -ie "s/^.*asSupport.*$//" ${MOTORSIM_IOC}/motorSimApp/src/Makefile
    sed -ie "s/autosave //" ${MOTORSIM_IOC}/motorSimApp/src/Makefile
    sed -ie "s/^ARCH.*$/ARCH=${EPICS_HOST_ARCH}/" ${MOTORSIM_IOC}/iocBoot/ioclocalhost/Makefile
    make -C ${MOTORSIM_IOC}
    touch ${MOTORSIM_IOC}/built
else
    echo "Using cached motorsim IOC"
fi
