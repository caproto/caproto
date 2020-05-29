
****************
Caproto-in-a-box
****************

.. highlight:: bash

.. contents::


Build a container with Buildah
------------------------------

To build a minimal container (based on Fedora) use the following bash script ::

   #! /usr/bin/bash
   set -e
   set -o xtrace


   buildah images
   buildah containers
   container=$(buildah from fedora)
   buildah run $container -- dnf -y install python3 ipython3 python3-pip python3-numpy python3-netifaces
   buildah run $container -- pip3 install caproto[standard]
   # this is the thing you want to change to spawn your IOC
   buildah config --cmd "python3 -m caproto.ioc_examples.simple --list-pvs" $container
   buildah unmount $container
   buildah commit $container caproto


Running containers with podman
------------------------------

By default ports are not forwarded out of the container, to do so run::

  podman run -dt -p 5064:5064/udp -p 5064:5064/tcp caproto


Running a sandbox with podman
-----------------------------

To generate a similar image, but for the bluesky collection stack::

  #! /usr/bin/bash
  set -e
  set -o xtrace


  container=$(buildah from fedora)
  buildah run $container -- dnf -y install python3 ipython3 python3-pip g++ gcc python3-PyQt5 python3-matplotlib python3-devel python3-netifaces python3-h5py python3-scipy python3-numcodecs python3-pandas
  buildah run $container -- pip3 install ophyd databroker bluesky caproto[standard]
  buildah run $container -- pip3 uninstall pyepics

  buildah commit $container bluesky

We can create a pod with private networking, our IOC and then attach to it via
bluesky ::

  podman pod create -n sandbox
  podman run -dt --pod sandbox caproto
  # this is unix / linux specefic
  podman run --pod sandbox -ti -v /tmp/.X11-unix/:/tmp/.X11-unix/ -e DISPLAY bluesky ipython3



If everything worked right, you should now have a caproto IOC running
in the pod and an IPython session running inside the pod with (networking wise)
but still able to pop up X11 windows.
