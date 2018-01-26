# Represent each CA Status Code as a namedtuple encapulating associated numeric
# codes and human-readable attributes.
from enum import IntEnum
from collections import namedtuple


CAStatusCode = namedtuple('CAStatusCode',
                          'name code code_with_severity severity success '
                          'defunct description')


class CASeverity(IntEnum):
    INFO = 3     # successful
    ERROR = 2    # failed; continue
    SUCCESS = 1  # successful
    WARNING = 0  # unsuccessful
    SEVERE = 4   # failed; quit
    FATAL = (ERROR | SEVERE)

    def __str__(self):
        return self.name


def _ca_status_code(name, severity: CASeverity, code, desc, *, defunct=False):
    '''Make a CAStatusCode

    Parameters
    ----------
    name : str
        Status code string name
    severity : CASeverity
        Severity level
    code : int
        Base code number (0 to 60, as of time of writing)
    desc : str
        User-friendlyish description
    defunct : bool, optional
        Indicates that current release servers and client library will not
        return this error code, but servers on earlier releases that
        communicate with current clients might still generate exceptions
        with these error constants.
    '''

    mask_msg = 0xFFF8
    mask_severity = 0x0007
    mask_success = 0x0001

    shift_message = 0x03
    shift_severity = 0x00
    shift_success = 0x00

    code_with_severity = (code << shift_message) & mask_msg
    code_with_severity |= (severity << shift_severity) & mask_severity

    success = (severity & mask_success) >> shift_success
    assert ((severity & mask_severity) >> shift_severity) == severity
    return CAStatusCode(name=name, code=code,
                        code_with_severity=code_with_severity,
                        severity=severity, success=success, description=desc,
                        defunct=defunct)


ECA_NORMAL = _ca_status_code(
    'ECA_NORMAL', severity=CASeverity.SUCCESS, code=0,
    desc="Normal successful completion")
ECA_MAXIOC = _ca_status_code(
    'ECA_MAXIOC', severity=CASeverity.ERROR, code=1,
    desc="Maximum simultaneous IOC connections exceeded",
    defunct=True)
ECA_UKNHOST = _ca_status_code(
    'ECA_UKNHOST', severity=CASeverity.ERROR, code=2,
    desc="Unknown internet host",
    defunct=True)
ECA_UKNSERV = _ca_status_code(
    'ECA_UKNSERV', severity=CASeverity.ERROR, code=3,
    desc="Unknown internet service",
    defunct=True)
ECA_SOCK = _ca_status_code(
    'ECA_SOCK', severity=CASeverity.ERROR, code=4,
    desc="Unable to allocate a new socket",
    defunct=True)
ECA_CONN = _ca_status_code(
    'ECA_CONN', severity=CASeverity.WARNING, code=5,
    desc="Unable to connect to internet host or service",
    defunct=True)
ECA_ALLOCMEM = _ca_status_code(
    'ECA_ALLOCMEM', severity=CASeverity.WARNING, code=6,
    desc="Unable to allocate additional dynamic memory")
ECA_UKNCHAN = _ca_status_code(
    'ECA_UKNCHAN', severity=CASeverity.WARNING, code=7,
    desc="Unknown IO channel",
    defunct=True)
ECA_UKNFIELD = _ca_status_code(
    'ECA_UKNFIELD', severity=CASeverity.WARNING, code=8,
    desc="Record field specified inappropriate for channel specified",
    defunct=True)
ECA_TOLARGE = _ca_status_code(
    'ECA_TOLARGE', severity=CASeverity.WARNING, code=9,
    desc=("The requested data transfer is greater than available memory "
          "or EPICS_CA_MAX_ARRAY_BYTES"))
ECA_TIMEOUT = _ca_status_code(
    'ECA_TIMEOUT', severity=CASeverity.WARNING, code=10,
    desc="User specified timeout on IO operation expired")
ECA_NOSUPPORT = _ca_status_code(
    'ECA_NOSUPPORT', severity=CASeverity.WARNING, code=11,
    desc="Sorry, that feature is planned but not supported at this time",
    defunct=True)
ECA_STRTOBIG = _ca_status_code(
    'ECA_STRTOBIG', severity=CASeverity.WARNING, code=12,
    desc="The supplied string is unusually large",
    defunct=True)
ECA_DISCONNCHID = _ca_status_code(
    'ECA_DISCONNCHID', severity=CASeverity.ERROR, code=13,
    desc=("The request was ignored because the specified channel is "
          "disconnected"),
    defunct=True)
ECA_BADTYPE = _ca_status_code(
    'ECA_BADTYPE', severity=CASeverity.ERROR, code=14,
    desc="The data type specifed is invalid")
ECA_CHIDNOTFND = _ca_status_code(
    'ECA_CHIDNOTFND', severity=CASeverity.INFO, code=15,
    desc="Remote Channel not found",
    defunct=True)
ECA_CHIDRETRY = _ca_status_code(
    'ECA_CHIDRETRY', severity=CASeverity.INFO, code=16,
    desc="Unable to locate all user specified channels",
    defunct=True)
ECA_INTERNAL = _ca_status_code(
    'ECA_INTERNAL', severity=CASeverity.FATAL, code=17,
    desc="Channel Access Internal Failure")
ECA_DBLCLFAIL = _ca_status_code(
    'ECA_DBLCLFAIL', severity=CASeverity.WARNING, code=18,
    desc="The requested local DB operation failed",
    defunct=True)
ECA_GETFAIL = _ca_status_code(
    'ECA_GETFAIL', severity=CASeverity.WARNING, code=19,
    desc="Channel read request failed")
ECA_PUTFAIL = _ca_status_code(
    'ECA_PUTFAIL', severity=CASeverity.WARNING, code=20,
    desc="Channel write request failed")
ECA_ADDFAIL = _ca_status_code(
    'ECA_ADDFAIL', severity=CASeverity.WARNING, code=21,
    desc="Channel subscription request failed",
    defunct=True)
ECA_BADCOUNT = _ca_status_code(
    'ECA_BADCOUNT', severity=CASeverity.WARNING, code=22,
    desc="Invalid element count requested")
ECA_BADSTR = _ca_status_code(
    'ECA_BADSTR', severity=CASeverity.ERROR, code=23,
    desc="Invalid string")
ECA_DISCONN = _ca_status_code(
    'ECA_DISCONN', severity=CASeverity.WARNING, code=24,
    desc="Virtual circuit disconnect")
ECA_DBLCHNL = _ca_status_code(
    'ECA_DBLCHNL', severity=CASeverity.WARNING, code=25,
    desc="Identical process variable name on multiple servers")
ECA_EVDISALLOW = _ca_status_code(
    'ECA_EVDISALLOW', severity=CASeverity.ERROR, code=26,
    desc=("Request inappropriate within subscription (monitor) update "
          "callback"))
ECA_BUILDGET = _ca_status_code(
    'ECA_BUILDGET', severity=CASeverity.WARNING, code=27,
    desc=("Database value get for that channel failed during channel "
          "search"),
    defunct=True)
ECA_NEEDSFP = _ca_status_code(
    'ECA_NEEDSFP', severity=CASeverity.WARNING, code=28,
    desc=("Unable to initialize without the vxWorks VX_FP_TASKtask "
          "option set"),
    defunct=True)
ECA_OVEVFAIL = _ca_status_code(
    'ECA_OVEVFAIL', severity=CASeverity.WARNING, code=29,
    desc=("Event queue overflow has prevented first pass event after "
          "event add"),
    defunct=True)
ECA_BADMONID = _ca_status_code(
    'ECA_BADMONID', severity=CASeverity.ERROR, code=30,
    desc="Bad event subscription (monitor) identifier")
ECA_NEWADDR = _ca_status_code(
    'ECA_NEWADDR', severity=CASeverity.WARNING, code=31,
    desc="Remote channel has new network address",
    defunct=True)
ECA_NEWCONN = _ca_status_code(
    'ECA_NEWCONN', severity=CASeverity.INFO, code=32,
    desc="New or resumed network connection",
    defunct=True)
ECA_NOCACTX = _ca_status_code(
    'ECA_NOCACTX', severity=CASeverity.WARNING, code=33,
    desc="Specified task isnt a member of a CA context",
    defunct=True)
ECA_DEFUNCT = _ca_status_code(
    'ECA_DEFUNCT', severity=CASeverity.FATAL, code=34,
    desc="Attempt to use defunct CA feature failed",
    defunct=True)
ECA_EMPTYSTR = _ca_status_code(
    'ECA_EMPTYSTR', severity=CASeverity.WARNING, code=35,
    desc="The supplied string is empty",
    defunct=True)
ECA_NOREPEATER = _ca_status_code(
    'ECA_NOREPEATER', severity=CASeverity.WARNING, code=36,
    desc=("Unable to spawn the CA repeater thread; auto reconnect will "
          "fail"),
    defunct=True)
ECA_NOCHANMSG = _ca_status_code(
    'ECA_NOCHANMSG', severity=CASeverity.WARNING, code=37,
    desc="No channel id match for search reply; search reply ignored",
    defunct=True)
ECA_DLCKREST = _ca_status_code(
    'ECA_DLCKREST', severity=CASeverity.WARNING, code=38,
    desc="Reseting dead connection; will try to reconnect",
    defunct=True)
ECA_SERVBEHIND = _ca_status_code(
    'ECA_SERVBEHIND', severity=CASeverity.WARNING, code=39,
    desc=("Server (IOC) has fallen behind or is not responding; still "
          "waiting"),
    defunct=True)
ECA_NOCAST = _ca_status_code(
    'ECA_NOCAST', severity=CASeverity.WARNING, code=40,
    desc="No internet interface with broadcast available",
    defunct=True)
ECA_BADMASK = _ca_status_code(
    'ECA_BADMASK', severity=CASeverity.ERROR, code=41,
    desc="Invalid event selection mask")
ECA_IODONE = _ca_status_code(
    'ECA_IODONE', severity=CASeverity.INFO, code=42,
    desc="IO operations have completed")
ECA_IOINPROGRESS = _ca_status_code(
    'ECA_IOINPROGRESS', severity=CASeverity.INFO, code=43,
    desc="IO operations are in progress")
ECA_BADSYNCGRP = _ca_status_code(
    'ECA_BADSYNCGRP', severity=CASeverity.ERROR, code=44,
    desc="Invalid synchronous group identifier")
ECA_PUTCBINPROG = _ca_status_code(
    'ECA_PUTCBINPROG', severity=CASeverity.ERROR, code=45,
    desc="Put callback timed out")
ECA_NORDACCESS = _ca_status_code(
    'ECA_NORDACCESS', severity=CASeverity.WARNING, code=46,
    desc="Read access denied")
ECA_NOWTACCESS = _ca_status_code(
    'ECA_NOWTACCESS', severity=CASeverity.WARNING, code=47,
    desc="Write access denied")
ECA_ANACHRONISM = _ca_status_code(
    'ECA_ANACHRONISM', severity=CASeverity.ERROR, code=48,
    desc="Requested feature is no longer supported")
ECA_NOSEARCHADDR = _ca_status_code(
    'ECA_NOSEARCHADDR', severity=CASeverity.WARNING, code=49,
    desc="Empty PV search address list")
ECA_NOCONVERT = _ca_status_code(
    'ECA_NOCONVERT', severity=CASeverity.WARNING, code=50,
    desc="No reasonable data conversion between client and server types")
ECA_BADCHID = _ca_status_code(
    'ECA_BADCHID', severity=CASeverity.ERROR, code=51,
    desc="Invalid channel identifier")
ECA_BADFUNCPTR = _ca_status_code(
    'ECA_BADFUNCPTR', severity=CASeverity.ERROR, code=52,
    desc="Invalid function pointer")
ECA_ISATTACHED = _ca_status_code(
    'ECA_ISATTACHED', severity=CASeverity.WARNING, code=53,
    desc="Thread is already attached to a client context")
ECA_UNAVAILINSERV = _ca_status_code(
    'ECA_UNAVAILINSERV', severity=CASeverity.WARNING, code=54,
    desc="Not supported by attached service")
ECA_CHANDESTROY = _ca_status_code(
    'ECA_CHANDESTROY', severity=CASeverity.WARNING, code=55,
    desc="User destroyed channel")
ECA_BADPRIORITY = _ca_status_code(
    'ECA_BADPRIORITY', severity=CASeverity.ERROR, code=56,
    desc="Invalid channel priority")
ECA_NOTTHREADED = _ca_status_code(
    'ECA_NOTTHREADED', severity=CASeverity.ERROR, code=57,
    desc=("Preemptive callback not enabled - additional threads may not "
          "join context"))
ECA_16KARRAYCLIENT = _ca_status_code(
    'ECA_16KARRAYCLIENT', severity=CASeverity.WARNING, code=58,
    desc=("Client’s protocol revision does not support transfers "
          "exceeding 16k bytes"))
ECA_CONNSEQTMO = _ca_status_code(
    'ECA_CONNSEQTMO', severity=CASeverity.WARNING, code=59,
    desc="Virtual circuit connection sequence aborted")
ECA_UNRESPTMO = _ca_status_code(
    'ECA_UNRESPTMO', severity=CASeverity.WARNING, code=60,
    desc="Virtual circuit unresponsive")


eca_value_to_status = {value.code_with_severity: value
                       for key, value in globals().items()
                       if key.startswith('ECA_')
                       }
