#!/bin/bash

set -vxeuo pipefail

git fetch --tags
python -m pip install --upgrade pip

for req in "$@"
do
    echo "Installing $req requirements..."
    python -m pip install -r "requirements-${req}.txt"
done

python -m pip install .
