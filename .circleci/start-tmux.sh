#!/bin/bash

set -e -x

export EPICS_TMUX_SESSION=IOCs

echo "Starting a new tmux session '${EPICS_TMUX_SESSION}'"
tmux new-session -d -s ${EPICS_TMUX_SESSION} /bin/bash

tmux set -g remain-on-exit on

echo "Starting the pyepics test IOC..."
tmux new-window -n 'pyepics-test_ioc' -c "$CI_SCRIPTS" \
    "source ${BASH_ENV}; \
    cd ${PYEPICS_IOC}/iocBoot/iocTestioc && \
    ${PYEPICS_IOC}/bin/${EPICS_HOST_ARCH}/testioc ./st.cmd"

echo "Starting the motorsim IOC..."
tmux new-window -n 'motorsim_ioc' -c "${CI_SCRIPTS}"  \
    "source ${BASH_ENV}; \
    cd ${MOTORSIM_IOC}/iocBoot/ioclocalhost && \
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
tmux new-window -c "${CI_SCRIPTS}" -n 'pyepics_sim' \
    "source ${BASH_ENV}; echo $PATH; which python; \
    cd "${PYEPICS_IOC}" && $HOME/caproto/caproto-venv/bin/python simulator.py"

echo "Done - check tmux session ${EPICS_TMUX_SESSION}"
