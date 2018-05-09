import datetime

DEFAULT_PROTOCOL_VERSION = 13
MAX_ID = 2**16  # max value of various integer IDs

# official IANA ports
EPICS_CA1_PORT, EPICS_CA2_PORT = 5064, 5065

EPICS2UNIX_EPOCH = 631152000.0
EPICS_EPOCH = datetime.datetime.utcfromtimestamp(EPICS2UNIX_EPOCH)

MAX_STRING_SIZE = 40
MAX_UNITS_SIZE = 8
MAX_ENUM_STRING_SIZE = 26
MAX_ENUM_STATES = 16
MAX_RECORD_LENGTH = 59  # from 3.14 on
MAX_UDP_RECV = 0xffff - 16

STALE_SEARCH_EXPIRATION = 10.0
# In theory (0xffff - 16) is allowed but in practice this can be too high
# without special system configuration. For more info on this and to see where
# this number comes from refer to
# https://stackoverflow.com/a/35335138/1221924
SEARCH_MAX_DATAGRAM_BYTES = 9216

# Servers send beacons at some maximum interval. ("Maximum delay between
# beacons will be limited by server specified parameter, but is commonly 15
# seconds.") Servers can be presumed dead and dropped by circuits and repeaters
# after some interval ("usually 30 seconds"). Reference:
# https://epics.anl.gov/docs/CAproto.html#secVCUnresponsive
SERVER_MIA_PRESUMED_DEAD = 60  # seconds


DO_REPLY = 10
NO_REPLY = 5
