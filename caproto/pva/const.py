import sys
import enum

MAX_INT32 = 2 ** 31 - 1
PVA_SERVER_PORT, PVA_BROADCAST_PORT = 5075, 5076


class Endian(str, enum.Enum):
    LITTLE_ENDIAN = '<'
    BIG_ENDIAN = '>'


# TODO: confusion with EndianFlag in messages.py
# TODO: 'little' and 'big' instead?

LITTLE_ENDIAN = Endian.LITTLE_ENDIAN
BIG_ENDIAN = Endian.BIG_ENDIAN
SYS_ENDIAN = (LITTLE_ENDIAN if sys.byteorder == 'little' else BIG_ENDIAN)
