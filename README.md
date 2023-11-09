# caproto

caproto: a bring-your-own-IO implementation of the EPICS Channel Access
protocol in pure Python

<img src="https://raw.githubusercontent.com/caproto/caproto/assets/caproto.svg" width="50%">

[![Build Status](https://github.com/caproto/caproto/actions/workflows/testing.yml/badge.svg)](https://github.com/caproto/caproto/actions/workflows/testing.yml)
[![codecov](https://codecov.io/gh/caproto/caproto/branch/master/graph/badge.svg)](https://codecov.io/gh/caproto/caproto)

[**Documentation**](https://caproto.github.io/caproto/)

## Overview

Caproto is an implementation of the
[EPICS](http://www.aps.anl.gov/epics/) Channel Access protocol for
distributed hardware control in pure Python with a "sans-I/O"
architecture.

Caproto is a toolkit for building Python programs that speak Channel
Access ("EPICS"). It includes a reusable core that encodes the Channel
Access protocol. It also includes several client and server
implementations built on that core. This layered design is inspired by
the broad effort in the Python community to write [sans-I/O
implementations of network protocols](http://sans-io.readthedocs.io/).
The EPICS (Experimental Physics and Industrial Control System) Channel
Access protocol is used in laboratories and companies [around the
world](https://en.wikipedia.org/wiki/EPICS#Facilities_using_EPICS) to
implement distributed control systems for devices such as large
telescopes, particle accelerators, and synchrotrons. Its
[roots](http://www.aps.anl.gov/epics/docs/APS2014/01-Introduction-to-EPICS.pdf)
go back to a 1988 meeting funded by the Reagan-era Strategic Defense
Initiative ("Star Wars").

The authors pronounce caproto "kah-proto" (not "C.A. proto").

Caproto is intended as a friendly entry-point to EPICS. It may be useful
for scientists who want to understand their hardware better, engineers
learning more about the EPICS community, and "makers" interested in
using it for hobby projects --- EPICS has been used for brewing beer and
keeping bees! At the same time, caproto is suitable for use at large
experimental facilities.

## Features

* A "sans-I/O" core of the EPICS Channel Access protocol.
* Multiple [client](https://caproto.github.io/caproto/v1.1.0/clients.html) and
  [server](https://caproto.github.io/caproto/v1.1.0/servers.html)
  implementations built on on the sans-I/O core.
    * asyncio client and server
    * Curio and trio server
    * Threaded client (a caproto-specific API and a pyepics-compat layer)
    * Synchronous (non-threaded) client
* A large tool suite for building pure Python IOCs.

## Try caproto in four lines

First verify that you have Python 3.8+.

``` bash
python3 --version
```

If necessary, install it by your method of choice (apt, Homebrew, conda,
etc.). Now install caproto:

``` bash
python3 -m pip install -U caproto
```

In one terminal, start an EPICS Input-Output Controller (IOC), which is
a server.

``` bash
python3 -m caproto.ioc_examples.simple --list-pvs
```

In another, use the command-line client:

``` bash
caproto-put simple:A 42
```

This sets the value to 42. See the
[documentation](https://caproto.github.io/caproto/) documentation for more
details on these tools.

## When to use caproto and when not to use caproto

caproto is good for:

* Writing simulation and testing IOCs
* Writing IOCs to interface with modern technology (could be minutes/hours vs
  days/weeks, depending on the application)
* Aiding debugging of connectivity and Channel Access issues
* Learning about the Channel Access protocol and EPICS in general
* Simple installation and usage (no build tools or knowledge thereof required)

caproto is not intended for the following, where epics-base excels:

* Mission-critical or performance-critical applications

## Who uses it

* SLAC LCLS
* BNL NSLS-II

## IOC examples

Here are some examples of IOCs in the wild.

These are in no particular order. Feel free to add yours to this list in a Pull Request!

| Description                                                                | Link                                              |
|----------------------------------------------------------------------------|---------------------------------------------------|
| Sim beamline from NSLS-II-SST                                              | https://github.com/NSLS-II-SST/sim_beamline       |
| archiver proxy                                                             | https://github.com/NSLS-II/archiver-proxy         |
| Variety of useful extensions for caproto   IOCs                            | https://github.com/canismarko/caproto-apps        |
| raspberry Pi IOCs                                                          | https://github.com/caproto/caproto-rpi            |
| EPICS to Kafka forwarder                                                   | https://github.com/ess-dmsc/forwarder             |
| FastCCD Support IOC                                                        | https://github.com/lbl-camera/fastccd_support_ioc |
| FCCD PSU IOC                                                               | https://github.com/lbl-camera/fccd_psu_ioc        |
| EPICS Archiver Appliance statistics IOC                                    | https://github.com/pcdshub/archstats/             |
| Fluke 985 particle counter IOC                                             | https://github.com/pcdshub/fluke_985              |
| LCLS RIX beamline calculation tools                                        | https://github.com/pcdshub/rixcalc                |
| Miscellaneous LCLS-specific simulation   IOC stuff                         | https://github.com/pcdshub/sim-ioc/               |
| LCLS Solid Attenuator System Calculator   IOC                              | https://github.com/pcdshub/solid-attenuator       |
| Converts motors and counters provided by   SPEC in server mode to EPICS PV | https://github.com/physwkim/speca                 |
| DHT-22                                                                     | https://github.com/prjemian/dhtioc                |
| A "lunchbox beamline" with   EPICs, ophyd and bluesky.                     | https://github.com/rosesyrett/lunchbox            |
| Simulacrum services                                                        | https://github.com/slaclab/simulacrum             |
| Austin Universal Robot at sector 25                                        | https://github.com/spc-group/ioc-austin           |
| Icarus Pressure Jump for NMR                                               | https://github.com/vstadnytskyi/icarus-nmr        |

### Client-related and miscellaneous examples

Here are some other caproto-adjacent things that may be of interest:

| Description                                                                   | Link                                                        |
|-------------------------------------------------------------------------------|-------------------------------------------------------------|
| Logger and extractor of time-series data   (e.g. EPICS PVs)                   | https://github.com/ASukhanov/apstrim                        |
| Prototype for logging PV changes and   emailing when rate limits are exceeded | https://github.com/NSLS-II/pv-watchdog                      |
| defunct image viewer (new maintainer   would be welcome)                      | https://github.com/klauer/caproto-image-viewer              |
| NICOS EPICS integration                                                       | https://github.com/mlz-ictrl/nicos/                         |
| cookiecutter for IOCs                                                         | https://github.com/pcdshub/cookiecutter-caproto-ioc         |
| startup script for above cookiecutter                                         | https://github.com/pcdshub/cookiecutter-caproto-ioc-startup |
| Proof-of-concept archiver                                                     | https://github.com/pklaus/caproto-archiver                  |
| Ancient and likely defunct Apple iOS   caproto IOCs                           | https://github.com/caproto/caproto_ios                      |


Others could be found through: https://github.com/caproto/caproto/network/dependents

## Command-line tools

caproto offers a variety of command-line tools. Here are their names and
epics-base equivalents:

| caproto              | epics-base              |
|----------------------|-------------------------|
| ``caproto-get``      | ``caget``               |
| ``caproto-put``      | ``caput``               |
| ``caproto-monitor``  | ``camonitor``           |
| ``caproto-repeater`` | ``caRepeater``          |
| ``caproto-shark``    | ``wireshark + cashark`` |
