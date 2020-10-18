export EPICS_CAS_INTF_ADDR_LIST=
export EPICS_CA_ADDR_LIST=
export EPICS_CAS_BEACON_ADDR_LIST=$EPICS_CA_ADDR_LIST
export EPICS_CA_AUTO_ADDR_LIST=YES
export EPICS_CAS_AUTO_BEACON_ADDR_LIST=YES

export CAPROTO_SKIP_MOTORSIM_TESTS=1

echo '--- azure environment ---'
env | grep EPIC
echo '--- azure environment ---'

source "$HOME/miniconda/etc/profile.d/conda.sh"
hash -r

conda activate test_env
