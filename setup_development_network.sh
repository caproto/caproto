#!/bin/bash
# Usage:   sudo setup_development_network.sh {add|remove} addr/bits
# Example: sudo setup_development_network.sh add 10.200.0.1/16

add_or_remove=$1
net_addr=$2
dev_name="epicsnet"

usage() {
   echo "Usage: sudo $0 {add|remove} addr/bits"
   exit 1;
}

if [ -z "$net_addr" ]; then
    usage;
fi

bcast_addr=$(python3 -c "import ipaddress, sys; print(str(ipaddress.ip_interface(sys.argv[1]).network))" $net_addr)


case "$add_or_remove" in 
add)
    echo "Adding '$dev_name' with network $net_addr..."
    set -x -e
    modprobe dummy
    ip link add dummy0 type dummy
    ip link set name $dev_name dev dummy0
    ip link show $dev_name
    ip addr add $net_addr brd + dev $dev_name label $dev_name:0
    ip link set $dev_name up
    ip addr list $dev_name
    set +e
    ip route add $bcast_addr dev $dev_name:0 || /bin/true
    iptables --list
    set +x
    echo "Done."
    ;;

remove)
    echo "Removing '$dev_name' with network $net_addr..."
    set -x -e
    ip addr list $dev_name
    ip route del $bcast_addr dev $dev_name:0
    ip link set $dev_name down
    ip addr del $net_addr brd + dev $dev_name label $dev_name:0
    ip link delete $dev_name type dummy
    rmmod dummy
    set +x +e
    echo "Done."
    ;;
*)
    usage
    ;;
esac
