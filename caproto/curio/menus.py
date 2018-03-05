import enum
import inspect


class menuPini(enum.IntEnum):
    NO = 0  # 'NO'
    YES = 1  # 'YES'
    RUN = 2  # 'RUN'
    RUNNING = 3  # 'RUNNING'
    PAUSE = 4  # 'PAUSE'
    PAUSED = 5  # 'PAUSED'


menuPini._strings = dict(
    NO='NO',
    YES='YES',
    RUN='RUN',
    RUNNING='RUNNING',
    PAUSE='PAUSE',
    PAUSED='PAUSED',
)


class menuFtype(enum.IntEnum):
    STRING = 0  # 'STRING'
    CHAR = 1  # 'CHAR'
    UCHAR = 2  # 'UCHAR'
    SHORT = 3  # 'SHORT'
    USHORT = 4  # 'USHORT'
    LONG = 5  # 'LONG'
    ULONG = 6  # 'ULONG'
    FLOAT = 7  # 'FLOAT'
    DOUBLE = 8  # 'DOUBLE'
    ENUM = 9  # 'ENUM'


menuFtype._strings = dict(
    STRING='STRING',
    CHAR='CHAR',
    UCHAR='UCHAR',
    SHORT='SHORT',
    USHORT='USHORT',
    LONG='LONG',
    ULONG='ULONG',
    FLOAT='FLOAT',
    DOUBLE='DOUBLE',
    ENUM='ENUM',
)


class seqSELM(enum.IntEnum):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


seqSELM._strings = dict(
    All='All',
    Specified='Specified',
    Mask='Mask',
)


class calcoutOOPT(enum.IntEnum):
    Every_Time = 0  # 'Every Time'
    On_Change = 1  # 'On Change'
    When_Zero = 2  # 'When Zero'
    When_Non_zero = 3  # 'When Non-zero'
    Transition_To_Zero = 4  # 'Transition To Zero'
    Transition_To_Non_zero = 5  # 'Transition To Non-zero'


calcoutOOPT._strings = dict(
    Every_Time='Every Time',
    On_Change='On Change',
    When_Zero='When Zero',
    When_Non_zero='When Non-zero',
    Transition_To_Zero='Transition To Zero',
    Transition_To_Non_zero='Transition To Non-zero',
)


class aSubLFLG(enum.IntEnum):
    IGNORE = 0  # 'IGNORE'
    READ = 1  # 'READ'


aSubLFLG._strings = dict(
    IGNORE='IGNORE',
    READ='READ',
)


class menuScan(enum.IntEnum):
    menuScanPassive = 0  # 'Passive'
    menuScanEvent = 1  # 'Event'
    menuScanI_O_Intr = 2  # 'I/O Intr'
    menuScan10_second = 3  # '10 second'
    menuScan5_second = 4  # '5 second'
    menuScan2_second = 5  # '2 second'
    menuScan1_second = 6  # '1 second'
    menuScan_5_second = 7  # '.5 second'
    menuScan_2_second = 8  # '.2 second'
    menuScan_1_second = 9  # '.1 second'


menuScan._strings = dict(
    menuScanPassive='Passive',
    menuScanEvent='Event',
    menuScanI_O_Intr='I/O Intr',
    menuScan10_second='10 second',
    menuScan5_second='5 second',
    menuScan2_second='2 second',
    menuScan1_second='1 second',
    menuScan_5_second='.5 second',
    menuScan_2_second='.2 second',
    menuScan_1_second='.1 second',
)


class menuIvoa(enum.IntEnum):
    Continue_normally = 0  # 'Continue normally'
    Don_t_drive_outputs = 1  # "Don't drive outputs"
    Set_output_to_IVOV = 2  # 'Set output to IVOV'


menuIvoa._strings = dict(
    Continue_normally='Continue normally',
    Don_t_drive_outputs="Don't drive outputs",
    Set_output_to_IVOV='Set output to IVOV',
)


class menuAlarmSevr(enum.IntEnum):
    NO_ALARM = 0  # 'NO_ALARM'
    MINOR = 1  # 'MINOR'
    MAJOR = 2  # 'MAJOR'
    INVALID = 3  # 'INVALID'


menuAlarmSevr._strings = dict(
    NO_ALARM='NO_ALARM',
    MINOR='MINOR',
    MAJOR='MAJOR',
    INVALID='INVALID',
)


class menuPost(enum.IntEnum):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


menuPost._strings = dict(
    OnChange='On Change',
    Always='Always',
)


class stringoutPOST(enum.IntEnum):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


stringoutPOST._strings = dict(
    OnChange='On Change',
    Always='Always',
)


class aoOIF(enum.IntEnum):
    Full = 0  # 'Full'
    Incremental = 1  # 'Incremental'


aoOIF._strings = dict(
    Full='Full',
    Incremental='Incremental',
)


class menuOmsl(enum.IntEnum):
    supervisory = 0  # 'supervisory'
    closed_loop = 1  # 'closed_loop'


menuOmsl._strings = dict(
    supervisory='supervisory',
    closed_loop='closed_loop',
)


class aSubEFLG(enum.IntEnum):
    NEVER = 0  # 'NEVER'
    ON_CHANGE = 1  # 'ON CHANGE'
    ALWAYS = 2  # 'ALWAYS'


aSubEFLG._strings = dict(
    NEVER='NEVER',
    ON_CHANGE='ON CHANGE',
    ALWAYS='ALWAYS',
)


class menuAlarmStat(enum.IntEnum):
    NO_ALARM = 0  # 'NO_ALARM'
    READ = 1  # 'READ'
    WRITE = 2  # 'WRITE'
    HIHI = 3  # 'HIHI'
    HIGH = 4  # 'HIGH'
    LOLO = 5  # 'LOLO'
    LOW = 6  # 'LOW'
    STATE = 7  # 'STATE'
    COS = 8  # 'COS'
    COMM = 9  # 'COMM'
    TIMEOUT = 10  # 'TIMEOUT'
    HWLIMIT = 11  # 'HWLIMIT'
    CALC = 12  # 'CALC'
    SCAN = 13  # 'SCAN'
    LINK = 14  # 'LINK'
    SOFT = 15  # 'SOFT'
    BAD_SUB = 16  # 'BAD_SUB'
    UDF = 17  # 'UDF'
    DISABLE = 18  # 'DISABLE'
    SIMM = 19  # 'SIMM'
    READ_ACCESS = 20  # 'READ_ACCESS'
    WRITE_ACCESS = 21  # 'WRITE_ACCESS'


menuAlarmStat._strings = dict(
    NO_ALARM='NO_ALARM',
    READ='READ',
    WRITE='WRITE',
    HIHI='HIHI',
    HIGH='HIGH',
    LOLO='LOLO',
    LOW='LOW',
    STATE='STATE',
    COS='COS',
    COMM='COMM',
    TIMEOUT='TIMEOUT',
    HWLIMIT='HWLIMIT',
    CALC='CALC',
    SCAN='SCAN',
    LINK='LINK',
    SOFT='SOFT',
    BAD_SUB='BAD_SUB',
    UDF='UDF',
    DISABLE='DISABLE',
    SIMM='SIMM',
    READ_ACCESS='READ_ACCESS',
    WRITE_ACCESS='WRITE_ACCESS',
)


class compressALG(enum.IntEnum):
    N_to_1_Low_Value = 0  # 'N to 1 Low Value'
    N_to_1_High_Value = 1  # 'N to 1 High Value'
    N_to_1_Average = 2  # 'N to 1 Average'
    Average = 3  # 'Average'
    Circular_Buffer = 4  # 'Circular Buffer'
    N_to_1_Median = 5  # 'N to 1 Median'


compressALG._strings = dict(
    N_to_1_Low_Value='N to 1 Low Value',
    N_to_1_High_Value='N to 1 High Value',
    N_to_1_Average='N to 1 Average',
    Average='Average',
    Circular_Buffer='Circular Buffer',
    N_to_1_Median='N to 1 Median',
)


class dfanoutSELM(enum.IntEnum):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


dfanoutSELM._strings = dict(
    All='All',
    Specified='Specified',
    Mask='Mask',
)


class aaiPOST(enum.IntEnum):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


aaiPOST._strings = dict(
    Always='Always',
    OnChange='On Change',
)


class waveformPOST(enum.IntEnum):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


waveformPOST._strings = dict(
    Always='Always',
    OnChange='On Change',
)


class calcoutINAV(enum.IntEnum):
    EXT_NC = 0  # 'Ext PV NC'
    EXT = 1  # 'Ext PV OK'
    LOC = 2  # 'Local PV'
    CON = 3  # 'Constant'


calcoutINAV._strings = dict(
    EXT_NC='Ext PV NC',
    EXT='Ext PV OK',
    LOC='Local PV',
    CON='Constant',
)


class menuPriority(enum.IntEnum):
    LOW = 0  # 'LOW'
    MEDIUM = 1  # 'MEDIUM'
    HIGH = 2  # 'HIGH'


menuPriority._strings = dict(
    LOW='LOW',
    MEDIUM='MEDIUM',
    HIGH='HIGH',
)


class selSELM(enum.IntEnum):
    Specified = 0  # 'Specified'
    High_Signal = 1  # 'High Signal'
    Low_Signal = 2  # 'Low Signal'
    Median_Signal = 3  # 'Median Signal'


selSELM._strings = dict(
    Specified='Specified',
    High_Signal='High Signal',
    Low_Signal='Low Signal',
    Median_Signal='Median Signal',
)


class aaoPOST(enum.IntEnum):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


aaoPOST._strings = dict(
    Always='Always',
    OnChange='On Change',
)


class fanoutSELM(enum.IntEnum):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


fanoutSELM._strings = dict(
    All='All',
    Specified='Specified',
    Mask='Mask',
)


class histogramCMD(enum.IntEnum):
    Read = 0  # 'Read'
    Clear = 1  # 'Clear'
    Start = 2  # 'Start'
    Stop = 3  # 'Stop'


histogramCMD._strings = dict(
    Read='Read',
    Clear='Clear',
    Start='Start',
    Stop='Stop',
)


class menuSimm(enum.IntEnum):
    NO = 0  # 'NO'
    YES = 1  # 'YES'
    RAW = 2  # 'RAW'


menuSimm._strings = dict(
    NO='NO',
    YES='YES',
    RAW='RAW',
)


class stringinPOST(enum.IntEnum):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


stringinPOST._strings = dict(
    OnChange='On Change',
    Always='Always',
)


class menuConvert(enum.IntEnum):
    NO_CONVERSION = 0  # 'NO CONVERSION'
    SLOPE = 1  # 'SLOPE'
    LINEAR = 2  # 'LINEAR'
    typeKdegF = 3  # 'typeKdegF'
    typeKdegC = 4  # 'typeKdegC'
    typeJdegF = 5  # 'typeJdegF'
    typeJdegC = 6  # 'typeJdegC'
    typeEdegF = 7  # 'typeEdegF(ixe only)'
    typeEdegC = 8  # 'typeEdegC(ixe only)'
    typeTdegF = 9  # 'typeTdegF'
    typeTdegC = 10  # 'typeTdegC'
    typeRdegF = 11  # 'typeRdegF'
    typeRdegC = 12  # 'typeRdegC'
    typeSdegF = 13  # 'typeSdegF'
    typeSdegC = 14  # 'typeSdegC'


menuConvert._strings = dict(
    NO_CONVERSION='NO CONVERSION',
    SLOPE='SLOPE',
    LINEAR='LINEAR',
    typeKdegF='typeKdegF',
    typeKdegC='typeKdegC',
    typeJdegF='typeJdegF',
    typeJdegC='typeJdegC',
    typeEdegF='typeEdegF(ixe only)',
    typeEdegC='typeEdegC(ixe only)',
    typeTdegF='typeTdegF',
    typeTdegC='typeTdegC',
    typeRdegF='typeRdegF',
    typeRdegC='typeRdegC',
    typeSdegF='typeSdegF',
    typeSdegC='typeSdegC',
)


class calcoutDOPT(enum.IntEnum):
    Use_VAL = 0  # 'Use CALC'
    Use_OVAL = 1  # 'Use OCAL'


calcoutDOPT._strings = dict(
    Use_VAL='Use CALC',
    Use_OVAL='Use OCAL',
)


class menuYesNo(enum.IntEnum):
    NO = 0  # 'NO'
    YES = 1  # 'YES'


menuYesNo._strings = dict(
    NO='NO',
    YES='YES',
)


menus = {name: menu for name, menu in globals().items()
         if inspect.isclass(menu) and issubclass(menu, enum.IntEnum)}
__all__ = ['menus'] + list(menus.keys())
