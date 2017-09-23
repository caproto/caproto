#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

mkfifo $HOME/testioc_pipe
sleep 10000 > $HOME/testioc_pipe &
cd "${PYEPICS_IOC}/iocBoot/iocTestioc" && ${PYEPICS_IOC}/bin/${EPICS_HOST_ARCH}/testioc ./st.cmd < $HOME/testioc_pipe &
echo help > $HOME/testioc_pipe

mkfifo $HOME/motorioc_pipe
sleep 10000 > $HOME/motorioc_pipe &
cd "${MOTORSIM_IOC}/iocBoot/ioclocalhost" && ${MOTORSIM_IOC}/bin/${EPICS_HOST_ARCH}/mtrSim ./st.cmd < $HOME/motorioc_pipe &
echo help > $HOME/motorioc_pipe

# if only tmux worked...
# tmux new-session -d -s IOCs /bin/bash
# echo "Starting the pyepics test IOC..."
# tmux new-window -c "${PYEPICS_IOC}/iocBoot/iocTestioc" \
#       "${PYEPICS_IOC}/bin/${EPICS_HOST_ARCH}/testioc ./st.cmd"
# 
# echo "Starting the motorsim IOC..."
# tmux new-window -c "${MOTORSIM_IOC}/iocBoot/ioclocalhost" \
#       "${MOTORSIM_IOC}/bin/${EPICS_HOST_ARCH}/mtrSim ./st.cmd"

# -- check that all IOCs have started --
until caget Py:ao1 sim:mtr1
do
  echo "Waiting for IOCs to startup..."
  sleep 0.5
done
echo "All IOCs are running!"

echo "Running pyepics simulator program..."
pip install pyepics
python ${PYEPICS_IOC}/simulator.py &
sleep 1
