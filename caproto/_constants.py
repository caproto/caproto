import datetime
import os

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
MAX_UDP_RECV = 0xFFFF - 16

# Max of ethernet and 802.{2,3} MTU 1500 - 20(IP header) - 8(UDP header)
SEARCH_MAX_DATAGRAM_BYTES = 1472

DO_REPLY = 10
NO_REPLY = 5

#
# NOTE: End of constants which should not be modified under any circumstances.
# NOTE: The following are *environment-configurable*, per-process constants.
#
STALE_SEARCH_EXPIRATION = float(
    os.environ.get("CAPROTO_STALE_SEARCH_EXPIRATION_SEC", 10.0)
)

# How long to wait between EchoRequest and EchoResponse before concluding that
# server is unresponsive, in seconds
RESPONSIVENESS_TIMEOUT = float(
    os.environ.get("CAPROTO_RESPONSIVENESS_TIMEOUT_SEC", 5)
)

# total per circuit not per subscription, by default.
MAX_TOTAL_SUBSCRIPTION_BACKLOG = int(
    os.environ.get("CAPROTO_MAX_TOTAL_SUBSCRIPTION_BACKLOG", 10000),
)
# If any channel has would have over this many elements when its subscription
# queue is full, warn about it:
SUBSCRIPTION_BACKLOG_WARN_THRESHOLD_ELEMENTS = int(
    os.environ.get(
        "CAPROTO_SUBSCRIPTION_BACKLOG_WARN_THRESHOLD_ELEMENTS",
        15_000_000,
    )
)
SUBSCRIPTION_BACKLOG_REDUCE_AT_WARN_LEVEL = bool(
    os.environ.get(
        "CAPROTO_SUBSCRIPTION_BACKLOG_REDUCE_AT_WARN_LEVEL",
        "y",
    ).lower() in ("y", "yes", "true", "1")
)
# default minimum, if we find ourselves above that threshold
MIN_SUBSCRIPTION_BACKLOG = int(os.environ.get("CAPROTO_MIN_SUBSCRIPTION_BACKLOG", 10))
# default, per subscription
MAX_SUBSCRIPTION_BACKLOG = int(os.environ.get("CAPROTO_MAX_SUBSCRIPTION_BACKLOG", 1000))
MAX_COMMAND_BACKLOG = int(os.environ.get("CAPROTO_MAX_COMMAND_BACKLOG", 10000))
