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

# Max of ethernet and 802.{2,3} MTU 1500 - 20(IP header) - 8(UDP header)
SEARCH_MAX_DATAGRAM_BYTES = 1472

# How long to wait between EchoRequest and EchoResponse before concluding that
# server is unresponsive.
RESPONSIVENESS_TIMEOUT = 5  # seconds

MAX_TOTAL_SUBSCRIPTION_BACKLOG = 10000  # total per circuit not per subscription
MAX_SUBSCRIPTION_BACKLOG = 1000  # per subscription
MAX_COMMAND_BACKLOG = 10000


DO_REPLY = 10
NO_REPLY = 5
