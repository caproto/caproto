export CI_TOP="$HOME/ci"

pushd $CI_TOP

cat > "epics_on_travis_custom_env.sh" <<'EOF'
export TRAVIS_BUILD_DIR="${HOME}"
export EPICS_CAS_INTF_ADDR_LIST=0.0.0.0
export EPICS_CA_ADDR_LIST=255.255.255.255
export EPICS_CAS_BEACON_ADDR_LIST=$EPICS_CA_ADDR_LIST
export EPICS_CA_AUTO_ADDR_LIST=NO
export EPICS_CAS_AUTO_BEACON_ADDR_LIST=NO
export EPICS_ON_TRAVIS_URL="https://github.com/klauer/epics-on-travis/releases/download/${EPICS_ON_TRAVIS_PKG}"
EOF

source setup_local_dev_env.sh
popd

echo '--- azure environment ---'
env | grep EPIC
echo '--- azure environment ---'
