#!/bin/bash
set -e -x

export EPICS_TMUX_SESSION=IOCs

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

echo "Starting a new tmux session '${EPICS_TMUX_SESSION}'"
tmux new-session -d -s ${EPICS_TMUX_SESSION} /bin/bash

echo "Starting the pyepics test IOC..."
tmux new-window -n 'pyepics-test_ioc' -c "${TRAVIS_BUILD_DIR}" \
    "source setup_local_dev_env.sh; \
    cd "${PYEPICS_IOC}/iocBoot/iocTestioc" && \
    ${PYEPICS_IOC}/bin/${EPICS_HOST_ARCH}/testioc ./st.cmd"

echo "Starting the motorsim IOC..."
tmux new-window -n 'motorsim_ioc' -c "${TRAVIS_BUILD_DIR}"  \
    "source setup_local_dev_env.sh; \
    cd "${MOTORSIM_IOC}/iocBoot/ioclocalhost" && \
    ${MOTORSIM_IOC}/bin/${EPICS_HOST_ARCH}/mtrSim ./st.cmd"

# -- check that all IOCs have started --
until caget Py:ao1
do
  echo "Waiting for pyepics test IOC to start..."
  sleep 0.5
done

until caget sim:mtr1
do
  echo "Waiting for motorsim IOC to start..."
  sleep 0.5
done
 
echo "All IOCs are running in tmux!"

echo "Running pyepics simulator program..."
tmux new-window -c "${TRAVIS_BUILD_DIR}" -n 'pyepics_sim' \
    "source setup_local_dev_env.sh; \
    source activate ${CONDA_DEFAULT_ENV}; env; \
    cd "${PYEPICS_IOC}" && python simulator.py"

echo "Done - check tmux session ${EPICS_TMUX_SESSION}"
