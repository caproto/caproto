#!/bin/bash
set -e -x

source $TRAVIS_BUILD_DIR/.ci/epics-config.sh

export PYEPICS_PID=0

rm -f $PYEPICS_IOC_PIPE $MOTORSIM_IOC_PIPE

function run_ioc() {
    set +x
    PIPE_PATH="$1"
    IOC_NAME="$2"
    IOC_PATH="$3"
    IOC_COMMAND="$4"
    TEST_PV="$5"

    echo ""
    echo ""
    echo ""
    echo "Executing IOC ${IOC_NAME}"
    echo "-------------------------"
    echo "pipe       ${PIPE_PATH}"
    echo "path       ${IOC_PATH}"
    echo "command    ${IOC_COMMAND}"
    echo "test_pv    ${TEST_PV}"
    echo ""
    echo ""
    set -x

    PID=0

    until caget ${TEST_PV}
    do
      if [[ -p "$PIPE_PATH" ]]; then
          echo "Retrying ${IOC_NAME} IOC"
          rm -f $PIPE_PATH
          if [ $PID -eq 0 ]; then
              echo "Failed to launch ${IOC_NAME}!"
              exit 1
          else
              kill -9 $PID || /bin/true
          fi
      fi

      mkfifo $PIPE_PATH
      sleep 10000 > $PIPE_PATH &

      cd "${IOC_PATH}" && ${IOC_COMMAND} < $PIPE_PATH &
      export PID=$!
      echo "${IOC_NAME} PID is $PID"
      echo help > $PIPE_PATH

      echo "Waiting for ${IOC_NAME} to start..."
      sleep 5.0
    done
}

run_ioc "$PYEPICS_IOC_PIPE" "pyepics-test-ioc" "${PYEPICS_IOC}/iocBoot/iocTestioc" \
    "${PYEPICS_IOC}/bin/${EPICS_HOST_ARCH}/testioc ./st.cmd" "Py:ao1"

run_ioc "$MOTORSIM_IOC_PIPE" "motorsim-ioc" "${MOTORSIM_IOC}/iocBoot/ioclocalhost" \
    "${MOTORSIM_IOC}/bin/${EPICS_HOST_ARCH}/mtrSim ./st.cmd" "sim:mtr1"

echo "All IOCs are running!"
