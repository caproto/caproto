# Contributing to caproto

## Setting up a development installation

The following have been tested on an Ubuntu 16.04 LTS VM.

1. Clone the repository.

```bash
git clone https://github.com/caproto/caproto
cd caproto
```

2. Create a Python 3 conda environment and install the test requirements.

```bash
conda create -n caproto python=3 numpy
source activate caproto
pip install -r requirements-test.txt
```

3. Run tests.

A small number of the tests test caproto against ``motorsim``. To skip these
tests, set the environment variable ``CAPROTO_SKIP_MOTORSIM_TESTS=1``.

```bash
CAPROTO_SKIP_MOTORSIM_TESTS=1 python run_tests.py -v
```
