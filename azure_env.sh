export CI_TOP="$BUILD_REPOSITORY_LOCALPATH/.ci"

pushd $CI_TOP

cat > "epics_on_travis_custom_env.sh" <<'EOF'
export TRAVIS_BUILD_DIR="${BUILD_REPOSITORY_LOCALPATH}"
export EPICS_CAS_INTF_ADDR_LIST=
export EPICS_CA_ADDR_LIST=
export EPICS_CAS_BEACON_ADDR_LIST=$EPICS_CA_ADDR_LIST
export EPICS_CA_AUTO_ADDR_LIST=YES
export EPICS_CAS_AUTO_BEACON_ADDR_LIST=YES
export EPICS_ON_TRAVIS_URL="https://github.com/klauer/epics-on-travis/releases/download/${EPICS_ON_TRAVIS_PKG}"

export CAPROTO_SKIP_MOTORSIM_TESTS=1
EOF

if [ -f "$HOME/epics/versions.sh" ]; then
    set -x
    . $HOME/epics/versions.sh
    set +x
fi

source setup_local_dev_env.sh
popd

echo '--- azure environment ---'
env | grep EPIC
echo '--- azure environment ---'
