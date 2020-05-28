
****************
Caproto-in-a-box
****************

.. highlight:: bash

.. contents::


Build a container with Buildah
------------------------------

To build a minimal container (based of Fedora) use the following bash script ::

   #! /usr/bin/bash
   set -e
   set -o xtrace


   buildah images
   buildah containers
   container=$(buildah from fedora)
   buildah run $container -- dnf -y install python3 ipython3 python3-pip g++ gcc
   buildah run $container -- pip3 install ophyd databroker bluesky caproto
   # this is the thing you want to change to spawn your IOC
   buildah config --cmd "python3 -m caproto.ioc_examples.simple --list-pvs -vvv" $container
   buildah commit $container caproto


Running container with podman
-----------------------------

Be default ports are not forwarded out of the container, do so launch as ::

  podman run -dt -p 5064:5064/udp -p 5064:5064/tcp caproto
