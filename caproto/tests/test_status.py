import caproto as ca
from caproto._status import eca_value_to_status


doc_statuss = [
    ('ECA_NORMAL', ca.CASeverity.SUCCESS, 0, 0x001),
    ('ECA_MAXIOC', ca.CASeverity.ERROR, 1, 0x00a),
    ('ECA_UKNHOST', ca.CASeverity.ERROR, 2, 0x012),
    ('ECA_UKNSERV', ca.CASeverity.ERROR, 3, 0x01a),
    ('ECA_SOCK', ca.CASeverity.ERROR, 4, 0x022),
    ('ECA_CONN', ca.CASeverity.WARNING, 5, 0x028),
    ('ECA_ALLOCMEM', ca.CASeverity.WARNING, 6, 0x030),
    ('ECA_UKNCHAN', ca.CASeverity.WARNING, 7, 0x038),
    ('ECA_UKNFIELD', ca.CASeverity.WARNING, 8, 0x040),
    ('ECA_TOLARGE', ca.CASeverity.WARNING, 9, 0x048),
    ('ECA_TIMEOUT', ca.CASeverity.WARNING, 10, 0x050),
    ('ECA_NOSUPPORT', ca.CASeverity.WARNING, 11, 0x058),
    ('ECA_STRTOBIG', ca.CASeverity.WARNING, 12, 0x060),
    ('ECA_DISCONNCHID', ca.CASeverity.ERROR, 13, 0x06a),
    ('ECA_BADTYPE', ca.CASeverity.ERROR, 14, 0x072),
    ('ECA_CHIDNOTFND', ca.CASeverity.INFO, 15, 0x07b),
    ('ECA_CHIDRETRY', ca.CASeverity.INFO, 16, 0x083),
    ('ECA_INTERNAL', ca.CASeverity.FATAL, 17, 0x08e),
    ('ECA_DBLCLFAIL', ca.CASeverity.WARNING, 18, 0x090),
    ('ECA_GETFAIL', ca.CASeverity.WARNING, 19, 0x098),
    ('ECA_PUTFAIL', ca.CASeverity.WARNING, 20, 0x0a0),
    ('ECA_ADDFAIL', ca.CASeverity.WARNING, 21, 0x0a8),
    ('ECA_BADCOUNT', ca.CASeverity.WARNING, 22, 0x0b0),
    ('ECA_BADSTR', ca.CASeverity.ERROR, 23, 0x0ba),
    ('ECA_DISCONN', ca.CASeverity.WARNING, 24, 0x0c0),
    ('ECA_DBLCHNL', ca.CASeverity.WARNING, 25, 0x0c8),
    ('ECA_EVDISALLOW', ca.CASeverity.ERROR, 26, 0x0d2),
    ('ECA_BUILDGET', ca.CASeverity.WARNING, 27, 0x0d8),
    ('ECA_NEEDSFP', ca.CASeverity.WARNING, 28, 0x0e0),
    ('ECA_OVEVFAIL', ca.CASeverity.WARNING, 29, 0x0e8),
    ('ECA_BADMONID', ca.CASeverity.ERROR, 30, 0x0f2),
    ('ECA_NEWADDR', ca.CASeverity.WARNING, 31, 0x0f8),
    ('ECA_NEWCONN', ca.CASeverity.INFO, 32, 0x103),
    ('ECA_NOCACTX', ca.CASeverity.WARNING, 33, 0x108),
    ('ECA_DEFUNCT', ca.CASeverity.FATAL, 34, 0x116),
    ('ECA_EMPTYSTR', ca.CASeverity.WARNING, 35, 0x118),
    ('ECA_NOREPEATER', ca.CASeverity.WARNING, 36, 0x120),
    ('ECA_NOCHANMSG', ca.CASeverity.WARNING, 37, 0x0128),
    ('ECA_DLCKREST', ca.CASeverity.WARNING, 38, 0x130),
    ('ECA_SERVBEHIND', ca.CASeverity.WARNING, 39, 0x138),
    ('ECA_NOCAST', ca.CASeverity.WARNING, 40, 0x140),
    ('ECA_BADMASK', ca.CASeverity.ERROR, 41, 0x14a),
    ('ECA_IODONE', ca.CASeverity.INFO, 42, 0x153),
    ('ECA_IOINPROGRESS', ca.CASeverity.INFO, 43, 0x15b),
    ('ECA_BADSYNCGRP', ca.CASeverity.ERROR, 44, 0x162),
    ('ECA_PUTCBINPROG', ca.CASeverity.ERROR, 45, 0x16a),
    ('ECA_NORDACCESS', ca.CASeverity.WARNING, 46, 0x170),
    ('ECA_NOWTACCESS', ca.CASeverity.WARNING, 47, 0x178),
    ('ECA_ANACHRONISM', ca.CASeverity.ERROR, 48, 0x182),
    ('ECA_NOSEARCHADDR', ca.CASeverity.WARNING, 49, 0x188),
    ('ECA_NOCONVERT', ca.CASeverity.WARNING, 50, 0x190),
    ('ECA_BADCHID', ca.CASeverity.ERROR, 51, 0x19a),
    ('ECA_BADFUNCPTR', ca.CASeverity.ERROR, 52, 0x1a2),
    ('ECA_ISATTACHED', ca.CASeverity.WARNING, 53, 0x1a8),
    ('ECA_UNAVAILINSERV', ca.CASeverity.WARNING, 54, 0x1b0),
    ('ECA_CHANDESTROY', ca.CASeverity.WARNING, 55, 0x1b8),
    ('ECA_BADPRIORITY', ca.CASeverity.ERROR, 56, 0x1c2),
    ('ECA_NOTTHREADED', ca.CASeverity.ERROR, 57, 0x1ca),
    ('ECA_16KARRAYCLIENT', ca.CASeverity.WARNING, 58, 0x1d0),
    ('ECA_CONNSEQTMO', ca.CASeverity.WARNING, 59, 0x1d8),  # TODO typo in docs 0x1d9
    ('ECA_UNRESPTMO', ca.CASeverity.WARNING, 60, 0x1e0),
]


def test_statuss():
    print(', '.join(hex(c) for c in sorted(eca_value_to_status.keys())))

    for value, st in sorted(eca_value_to_status.items()):
        print(hex(value), st)

    missing = []
    for name, severity, code, code_with_severity in doc_statuss:
        try:
            code_nt = eca_value_to_status[code_with_severity]
        except KeyError:
            missing.append('{} ({}/0x{:x})'.format(name, code,
                                                   code_with_severity))
            continue

        assert code_nt.name == name
        assert code_nt.severity == severity
        assert code_nt.code == code
        assert code_nt.code_with_severity == code_with_severity

    assert not missing, ('Missing status code entries: {}'
                         ''.format(', '.join(missing)))

    assert len(eca_value_to_status) == len(doc_statuss)
