# Contributing to caproto

## Setting up a development installation

The following have been tested on an Ubuntu 16.04 LTS VM.

1. Clone the repository.

```bash
git clone https://github.com/caproto/caproto
cd caproto
```

2. Install the EPICS build dependencies.

```bash
sudo apt-get install curl libreadline6-dev libncurses5-dev perl re2c tmux strace
```

3. Set environment variables.

```bash
source setup_local_dev_env.sh
```

4. Install EPICS dependencies.

```bash
bash .ci/install-epics-base.sh
bash .ci/install-epics-modules.sh
bash .ci/install-epics-modules.sh
bash .ci/install-epics-iocs.sh
```

5. Run the IOCs that the tests will communicate with.

```bash
bash .ci/run-epics-iocs.sh
```

6. Create a Python 3 conda environment and install the test requirements.

```bash
conda create -n caproto python=3 numpy
source activate caproto
pip install -r test-requirements.txt
```

7. Run the pyepics 'simulator' and continually updates some test PVs to be
   monitored.

```bash
bash .ci/run-pyepics-simulator.sh
```

8. Run tests.

```bash
python run_tests.py -v
```
