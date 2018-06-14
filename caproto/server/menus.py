import enum
import inspect


class Menu(enum.IntEnum):
    @classmethod
    def _set_strings(cls, value_to_string):
        cls._string_dict = value_to_string
        cls._string_tuple = tuple(value_to_string.values())

    @classmethod
    def get_string_dict(cls):
        "Dict of menu_item to display_string"
        return cls._string_dict

    @classmethod
    def get_string_tuple(cls):
        "Ordered tuple of menu display strings"
        return cls._string_tuple


class NotImplementedMenu(Menu):
    'These are placeholders for menus not yet converted.'
    PLACEHOLDER = 0


NotImplementedMenu._set_strings(
    {
        NotImplementedMenu.PLACEHOLDER: 'NOT_IMPLEMENTED',
    }
)


class aSubEFLG(Menu):
    NEVER = 0  # 'NEVER'
    ON_CHANGE = 1  # 'ON CHANGE'
    ALWAYS = 2  # 'ALWAYS'


aSubEFLG._set_strings(
    {
        aSubEFLG.NEVER: 'NEVER',
        aSubEFLG.ON_CHANGE: 'ON CHANGE',
        aSubEFLG.ALWAYS: 'ALWAYS',
    }
)


class aSubLFLG(Menu):
    IGNORE = 0  # 'IGNORE'
    READ = 1  # 'READ'


aSubLFLG._set_strings(
    {
        aSubLFLG.IGNORE: 'IGNORE',
        aSubLFLG.READ: 'READ',
    }
)


class aaiPOST(Menu):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


aaiPOST._set_strings(
    {
        aaiPOST.Always: 'Always',
        aaiPOST.OnChange: 'On Change',
    }
)


class aaoPOST(Menu):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


aaoPOST._set_strings(
    {
        aaoPOST.Always: 'Always',
        aaoPOST.OnChange: 'On Change',
    }
)


class aoOIF(Menu):
    Full = 0  # 'Full'
    Incremental = 1  # 'Incremental'


aoOIF._set_strings(
    {
        aoOIF.Full: 'Full',
        aoOIF.Incremental: 'Incremental',
    }
)


class calcoutDOPT(Menu):
    Use_VAL = 0  # 'Use CALC'
    Use_OVAL = 1  # 'Use OCAL'


calcoutDOPT._set_strings(
    {
        calcoutDOPT.Use_VAL: 'Use CALC',
        calcoutDOPT.Use_OVAL: 'Use OCAL',
    }
)


class calcoutINAV(Menu):
    EXT_NC = 0  # 'Ext PV NC'
    EXT = 1  # 'Ext PV OK'
    LOC = 2  # 'Local PV'
    CON = 3  # 'Constant'


calcoutINAV._set_strings(
    {
        calcoutINAV.EXT_NC: 'Ext PV NC',
        calcoutINAV.EXT: 'Ext PV OK',
        calcoutINAV.LOC: 'Local PV',
        calcoutINAV.CON: 'Constant',
    }
)


class calcoutOOPT(Menu):
    Every_Time = 0  # 'Every Time'
    On_Change = 1  # 'On Change'
    When_Zero = 2  # 'When Zero'
    When_Non_zero = 3  # 'When Non-zero'
    Transition_To_Zero = 4  # 'Transition To Zero'
    Transition_To_Non_zero = 5  # 'Transition To Non-zero'


calcoutOOPT._set_strings(
    {
        calcoutOOPT.Every_Time: 'Every Time',
        calcoutOOPT.On_Change: 'On Change',
        calcoutOOPT.When_Zero: 'When Zero',
        calcoutOOPT.When_Non_zero: 'When Non-zero',
        calcoutOOPT.Transition_To_Zero: 'Transition To Zero',
        calcoutOOPT.Transition_To_Non_zero: 'Transition To Non-zero',
    }
)


class compressALG(Menu):
    N_to_1_Low_Value = 0  # 'N to 1 Low Value'
    N_to_1_High_Value = 1  # 'N to 1 High Value'
    N_to_1_Average = 2  # 'N to 1 Average'
    Average = 3  # 'Average'
    Circular_Buffer = 4  # 'Circular Buffer'
    N_to_1_Median = 5  # 'N to 1 Median'


compressALG._set_strings(
    {
        compressALG.N_to_1_Low_Value: 'N to 1 Low Value',
        compressALG.N_to_1_High_Value: 'N to 1 High Value',
        compressALG.N_to_1_Average: 'N to 1 Average',
        compressALG.Average: 'Average',
        compressALG.Circular_Buffer: 'Circular Buffer',
        compressALG.N_to_1_Median: 'N to 1 Median',
    }
)


class dfanoutSELM(Menu):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


dfanoutSELM._set_strings(
    {
        dfanoutSELM.All: 'All',
        dfanoutSELM.Specified: 'Specified',
        dfanoutSELM.Mask: 'Mask',
    }
)


class fanoutSELM(Menu):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


fanoutSELM._set_strings(
    {
        fanoutSELM.All: 'All',
        fanoutSELM.Specified: 'Specified',
        fanoutSELM.Mask: 'Mask',
    }
)


class histogramCMD(Menu):
    Read = 0  # 'Read'
    Clear = 1  # 'Clear'
    Start = 2  # 'Start'
    Stop = 3  # 'Stop'


histogramCMD._set_strings(
    {
        histogramCMD.Read: 'Read',
        histogramCMD.Clear: 'Clear',
        histogramCMD.Start: 'Start',
        histogramCMD.Stop: 'Stop',
    }
)


class menuAlarmSevr(Menu):
    NO_ALARM = 0  # 'NO_ALARM'
    MINOR = 1  # 'MINOR'
    MAJOR = 2  # 'MAJOR'
    INVALID = 3  # 'INVALID'


menuAlarmSevr._set_strings(
    {
        menuAlarmSevr.NO_ALARM: 'NO_ALARM',
        menuAlarmSevr.MINOR: 'MINOR',
        menuAlarmSevr.MAJOR: 'MAJOR',
        menuAlarmSevr.INVALID: 'INVALID',
    }
)


class menuAlarmStat(Menu):
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


menuAlarmStat._set_strings(
    {
        menuAlarmStat.NO_ALARM: 'NO_ALARM',
        menuAlarmStat.READ: 'READ',
        menuAlarmStat.WRITE: 'WRITE',
        menuAlarmStat.HIHI: 'HIHI',
        menuAlarmStat.HIGH: 'HIGH',
        menuAlarmStat.LOLO: 'LOLO',
        menuAlarmStat.LOW: 'LOW',
        menuAlarmStat.STATE: 'STATE',
        menuAlarmStat.COS: 'COS',
        menuAlarmStat.COMM: 'COMM',
        menuAlarmStat.TIMEOUT: 'TIMEOUT',
        menuAlarmStat.HWLIMIT: 'HWLIMIT',
        menuAlarmStat.CALC: 'CALC',
        menuAlarmStat.SCAN: 'SCAN',
        menuAlarmStat.LINK: 'LINK',
        menuAlarmStat.SOFT: 'SOFT',
        menuAlarmStat.BAD_SUB: 'BAD_SUB',
        menuAlarmStat.UDF: 'UDF',
        menuAlarmStat.DISABLE: 'DISABLE',
        menuAlarmStat.SIMM: 'SIMM',
        menuAlarmStat.READ_ACCESS: 'READ_ACCESS',
        menuAlarmStat.WRITE_ACCESS: 'WRITE_ACCESS',
    }
)


class menuConvert(Menu):
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


menuConvert._set_strings(
    {
        menuConvert.NO_CONVERSION: 'NO CONVERSION',
        menuConvert.SLOPE: 'SLOPE',
        menuConvert.LINEAR: 'LINEAR',
        menuConvert.typeKdegF: 'typeKdegF',
        menuConvert.typeKdegC: 'typeKdegC',
        menuConvert.typeJdegF: 'typeJdegF',
        menuConvert.typeJdegC: 'typeJdegC',
        menuConvert.typeEdegF: 'typeEdegF(ixe only)',
        menuConvert.typeEdegC: 'typeEdegC(ixe only)',
        menuConvert.typeTdegF: 'typeTdegF',
        menuConvert.typeTdegC: 'typeTdegC',
        menuConvert.typeRdegF: 'typeRdegF',
        menuConvert.typeRdegC: 'typeRdegC',
        menuConvert.typeSdegF: 'typeSdegF',
        menuConvert.typeSdegC: 'typeSdegC',
    }
)


class menuFtype(Menu):
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


menuFtype._set_strings(
    {
        menuFtype.STRING: 'STRING',
        menuFtype.CHAR: 'CHAR',
        menuFtype.UCHAR: 'UCHAR',
        menuFtype.SHORT: 'SHORT',
        menuFtype.USHORT: 'USHORT',
        menuFtype.LONG: 'LONG',
        menuFtype.ULONG: 'ULONG',
        menuFtype.FLOAT: 'FLOAT',
        menuFtype.DOUBLE: 'DOUBLE',
        menuFtype.ENUM: 'ENUM',
    }
)


class menuIvoa(Menu):
    Continue_normally = 0  # 'Continue normally'
    Don_t_drive_outputs = 1  # "Don't drive outputs"
    Set_output_to_IVOV = 2  # 'Set output to IVOV'


menuIvoa._set_strings(
    {
        menuIvoa.Continue_normally: 'Continue normally',
        menuIvoa.Don_t_drive_outputs: "Don't drive outputs",
        menuIvoa.Set_output_to_IVOV: 'Set output to IVOV',
    }
)


class menuOmsl(Menu):
    supervisory = 0  # 'supervisory'
    closed_loop = 1  # 'closed_loop'


menuOmsl._set_strings(
    {
        menuOmsl.supervisory: 'supervisory',
        menuOmsl.closed_loop: 'closed_loop',
    }
)


class menuPini(Menu):
    NO = 0  # 'NO'
    YES = 1  # 'YES'
    RUN = 2  # 'RUN'
    RUNNING = 3  # 'RUNNING'
    PAUSE = 4  # 'PAUSE'
    PAUSED = 5  # 'PAUSED'


menuPini._set_strings(
    {
        menuPini.NO: 'NO',
        menuPini.YES: 'YES',
        menuPini.RUN: 'RUN',
        menuPini.RUNNING: 'RUNNING',
        menuPini.PAUSE: 'PAUSE',
        menuPini.PAUSED: 'PAUSED',
    }
)


class menuPost(Menu):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


menuPost._set_strings(
    {
        menuPost.OnChange: 'On Change',
        menuPost.Always: 'Always',
    }
)


class menuPriority(Menu):
    LOW = 0  # 'LOW'
    MEDIUM = 1  # 'MEDIUM'
    HIGH = 2  # 'HIGH'


menuPriority._set_strings(
    {
        menuPriority.LOW: 'LOW',
        menuPriority.MEDIUM: 'MEDIUM',
        menuPriority.HIGH: 'HIGH',
    }
)


class menuScan(Menu):
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


menuScan._set_strings(
    {
        menuScan.menuScanPassive: 'Passive',
        menuScan.menuScanEvent: 'Event',
        menuScan.menuScanI_O_Intr: 'I/O Intr',
        menuScan.menuScan10_second: '10 second',
        menuScan.menuScan5_second: '5 second',
        menuScan.menuScan2_second: '2 second',
        menuScan.menuScan1_second: '1 second',
        menuScan.menuScan_5_second: '.5 second',
        menuScan.menuScan_2_second: '.2 second',
        menuScan.menuScan_1_second: '.1 second',
    }
)


class menuSimm(Menu):
    NO = 0  # 'NO'
    YES = 1  # 'YES'
    RAW = 2  # 'RAW'


menuSimm._set_strings(
    {
        menuSimm.NO: 'NO',
        menuSimm.YES: 'YES',
        menuSimm.RAW: 'RAW',
    }
)


class menuYesNo(Menu):
    NO = 0  # 'NO'
    YES = 1  # 'YES'


menuYesNo._set_strings(
    {
        menuYesNo.NO: 'NO',
        menuYesNo.YES: 'YES',
    }
)


class selSELM(Menu):
    Specified = 0  # 'Specified'
    High_Signal = 1  # 'High Signal'
    Low_Signal = 2  # 'Low Signal'
    Median_Signal = 3  # 'Median Signal'


selSELM._set_strings(
    {
        selSELM.Specified: 'Specified',
        selSELM.High_Signal: 'High Signal',
        selSELM.Low_Signal: 'Low Signal',
        selSELM.Median_Signal: 'Median Signal',
    }
)


class seqSELM(Menu):
    All = 0  # 'All'
    Specified = 1  # 'Specified'
    Mask = 2  # 'Mask'


seqSELM._set_strings(
    {
        seqSELM.All: 'All',
        seqSELM.Specified: 'Specified',
        seqSELM.Mask: 'Mask',
    }
)


class stringinPOST(Menu):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


stringinPOST._set_strings(
    {
        stringinPOST.OnChange: 'On Change',
        stringinPOST.Always: 'Always',
    }
)


class stringoutPOST(Menu):
    OnChange = 0  # 'On Change'
    Always = 1  # 'Always'


stringoutPOST._set_strings(
    {
        stringoutPOST.OnChange: 'On Change',
        stringoutPOST.Always: 'Always',
    }
)


class waveformPOST(Menu):
    Always = 0  # 'Always'
    OnChange = 1  # 'On Change'


waveformPOST._set_strings(
    {
        waveformPOST.Always: 'Always',
        waveformPOST.OnChange: 'On Change',
    }
)


acalcoutDOPT = NotImplementedMenu
acalcoutINAV = NotImplementedMenu
acalcoutOOPT = NotImplementedMenu
acalcoutSIZE = NotImplementedMenu
acalcoutWAIT = NotImplementedMenu
asynAUTOCONNECT = NotImplementedMenu
asynCONNECT = NotImplementedMenu
asynENABLE = NotImplementedMenu
asynEOMREASON = NotImplementedMenu
asynFMT = NotImplementedMenu
asynINTERFACE = NotImplementedMenu
asynTMOD = NotImplementedMenu
asynTRACE = NotImplementedMenu
digitelBAKS = NotImplementedMenu
digitelBKIN = NotImplementedMenu
digitelCMOR = NotImplementedMenu
digitelDSPL = NotImplementedMenu
digitelKLCK = NotImplementedMenu
digitelMODR = NotImplementedMenu
digitelMODS = NotImplementedMenu
digitelPTYP = NotImplementedMenu
digitelS1MS = NotImplementedMenu
digitelS1VS = NotImplementedMenu
digitelS3BS = NotImplementedMenu
digitelSET1 = NotImplementedMenu
digitelTYPE = NotImplementedMenu
epidFeedbackMode = NotImplementedMenu
epidFeedbackState = NotImplementedMenu
genSubEFLG = NotImplementedMenu
genSubLFLG = NotImplementedMenu
gpibACMD = NotImplementedMenu
gpibUCMD = NotImplementedMenu
mcaCHAS = NotImplementedMenu
mcaERAS = NotImplementedMenu
mcaMODE = NotImplementedMenu
mcaREAD = NotImplementedMenu
mcaREAD = NotImplementedMenu
mcaREAD = NotImplementedMenu
mcaSTRT = NotImplementedMenu
mcaSTRT = NotImplementedMenu
mcaSTRT = NotImplementedMenu
mcaSTRT = NotImplementedMenu
motorDIR = NotImplementedMenu
motorFOFF = NotImplementedMenu
motorRMOD = NotImplementedMenu
motorSET = NotImplementedMenu
motorSPMG = NotImplementedMenu
motorSTUP = NotImplementedMenu
motorTORQ = NotImplementedMenu
motorUEIP = NotImplementedMenu
scalcoutDOPT = NotImplementedMenu
scalcoutINAV = NotImplementedMenu
scalcoutOOPT = NotImplementedMenu
scalcoutWAIT = NotImplementedMenu
scalerCNT = NotImplementedMenu
scalerCONT = NotImplementedMenu
scalerD1 = NotImplementedMenu
scalerG1 = NotImplementedMenu
serialBAUD = NotImplementedMenu
serialDBIT = NotImplementedMenu
serialFCTL = NotImplementedMenu
serialIX = NotImplementedMenu
serialMCTL = NotImplementedMenu
serialPRTY = NotImplementedMenu
serialSBIT = NotImplementedMenu
sscanACQM = NotImplementedMenu
sscanACQT = NotImplementedMenu
sscanCMND = NotImplementedMenu
sscanDSTATE = NotImplementedMenu
sscanFAZE = NotImplementedMenu
sscanFFO = NotImplementedMenu
sscanFPTS = NotImplementedMenu
sscanLINKWAIT = NotImplementedMenu
sscanNOYES = NotImplementedMenu
sscanP1AR = NotImplementedMenu
sscanP1NV = NotImplementedMenu
sscanP1SM = NotImplementedMenu
sscanPASM = NotImplementedMenu
sscanPAUS = NotImplementedMenu
sseqLNKV = NotImplementedMenu
sseqSELM = NotImplementedMenu
sseqWAIT = NotImplementedMenu
swaitDOPT = NotImplementedMenu
swaitINAV = NotImplementedMenu
swaitOOPT = NotImplementedMenu
tableGEOM = NotImplementedMenu
tableSET = NotImplementedMenu
timestampTST = NotImplementedMenu
transformCOPT = NotImplementedMenu
transformIVLA = NotImplementedMenu
vmeAMOD = NotImplementedMenu
vmeDSIZ = NotImplementedMenu
vmeRDWT = NotImplementedMenu
vsOFFON = NotImplementedMenu
vsTYPE = NotImplementedMenu


menus = {name: menu for name, menu in globals().items()
         if menu is not Menu and
         inspect.isclass(menu) and (issubclass(menu, Menu) or
                                    menu is NotImplementedMenu)
         }
__all__ = ['menus'] + list(menus.keys())
