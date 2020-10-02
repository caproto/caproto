#!/bin/bash

GITHUB_IO=../github.io
OLD_ENV=caproto-3.6
NEW_ENV=caproto

conda activate $OLD_ENV

for version in v0.1.2 v0.2.3 v0.3.4 v0.4.0 v0.4.1 v0.4.2 v0.4.3 v0.4.4 v0.5.0 v0.5.1 v0.5.2 v0.6.0; do
    if [[ $version == "v0.5.0" ]]; then
        conda activate $NEW_ENV
    fi

    kill `pgrep -f random_walk` || true
    git reset --hard $version
    if [ ! `grep 'doctr_versions_menu' source/conf.py` ]; then
        sed -i -e '/^extensions = .*/a\
            "doctr_versions_menu",' source/conf.py
    fi
    sed -i -e 's/201[789]/2020/g' source/conf.py
    rm -rf build && make html
    # it's clean, really!
    find build/html -type f -name "*.html" -exec sed -i -e 's/+0\.g........\.dirty//g' {} \;
    find build/html -type f -name "*.js" -exec sed -i -e 's/+0\.g........\.dirty//g' {} \;
    find build/html -name doctr-versions-menu.js -exec sed -i -e "s#'/versions.json#'/caproto/versions.json#" {} \;
    cp -R build/html/ $GITHUB_IO/caproto/$version/
done
