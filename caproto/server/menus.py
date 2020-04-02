import enum
import inspect

from .._constants import MAX_ENUM_STATES


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
        """
        Ordered tuple of menu display strings

        Note that this limits the maximum number of enum states reported to
        that which can be sent over Channel Access (MAX_ENUM_STATES).  While it
        is still possible to use more than that limit internally, it is not
        recommended to do so.
        """
        return cls._string_tuple[:MAX_ENUM_STATES]


class NotImplementedMenu(Menu):
    'These are placeholders for menus not yet converted.'
    PLACEHOLDER = 0


NotImplementedMenu._set_strings(
    {
        NotImplementedMenu.PLACEHOLDER: 'NOT_IMPLEMENTED',
    }
)


def create_menu(name, _base=Menu, **options):
    'Dynamically create a Menu'
    option_to_value = {name: value for name, (value, _) in options.items()}
    option_to_string = {name: string for name, (_, string) in options.items()}
    cls = _base(name, option_to_value)
    cls._set_strings(option_to_string)
    return cls


aSubEFLG = create_menu(
    "aSubEFLG",
    NEVER=(0, "NEVER"),
    ON_CHANGE=(1, "ON CHANGE"),
    ALWAYS=(2, "ALWAYS")
)
aSubLFLG = create_menu(
    "aSubLFLG",
    IGNORE=(0, "IGNORE"),
    READ=(1, "READ")
)
aaiPOST = create_menu(
    "aaiPOST",
    Always=(0, "Always"),
    OnChange=(1, "On Change")
)
aaoPOST = create_menu(
    "aaoPOST",
    Always=(0, "Always"),
    OnChange=(1, "On Change")
)
aoOIF = create_menu(
    "aoOIF",
    Full=(0, "Full"),
    Incremental=(1, "Incremental")
)
asynAUTOCONNECT = create_menu(
    "asynAUTOCONNECT",
    noAutoConnect=(0, "noAutoConnect"),
    autoConnect=(1, "autoConnect")
)
asynCONNECT = create_menu(
    "asynCONNECT",
    Disconnect=(0, "Disconnect"),
    Connect=(1, "Connect")
)
asynENABLE = create_menu(
    "asynENABLE",
    Disable=(0, "Disable"),
    Enable=(1, "Enable")
)
asynEOMREASON = create_menu(
    "asynEOMREASON",
    none=(0, "None"),
    CNT=(1, "Count"),
    EOS=(2, "Eos"),
    CNTEOS=(3, "Count Eos"),
    END=(4, "End"),
    CNTEND=(5, "Count End"),
    EOSEND=(6, "Eos End"),
    CNTEOSEND=(7, "Count Eos End")
)
asynFMT = create_menu(
    "asynFMT",
    ASCII=(0, "ASCII"),
    Hybrid=(1, "Hybrid"),
    Binary=(2, "Binary")
)
asynINTERFACE = create_menu(
    "asynINTERFACE",
    OCTET=(0, "asynOctet"),
    INT32=(1, "asynInt32"),
    UINT32=(2, "asynUInt32Digital"),
    FLOAT64=(3, "asynFloat64")
)
asynTMOD = create_menu(
    "asynTMOD",
    Write_Read=(0, "Write/Read"),
    Write=(1, "Write"),
    Read=(2, "Read"),
    Flush=(3, "Flush"),
    NoIO=(4, "NoI/O")
)
asynTRACE = create_menu(
    "asynTRACE",
    Off=(0, "Off"),
    On=(1, "On")
)
bufferingALG = create_menu(
    "bufferingALG",
    FIFO=(0, "FIFO Buffer"),
    LIFO=(1, "LIFO Buffer")
)
calcoutDOPT = create_menu(
    "calcoutDOPT",
    Use_VAL=(0, "Use CALC"),
    Use_OVAL=(1, "Use OCAL")
)
calcoutINAV = create_menu(
    "calcoutINAV",
    EXT_NC=(0, "Ext PV NC"),
    EXT=(1, "Ext PV OK"),
    LOC=(2, "Local PV"),
    CON=(3, "Constant")
)
calcoutOOPT = create_menu(
    "calcoutOOPT",
    Every_Time=(0, "Every Time"),
    On_Change=(1, "On Change"),
    When_Zero=(2, "When Zero"),
    When_Non_zero=(3, "When Non-zero"),
    Transition_To_Zero=(4, "Transition To Zero"),
    Transition_To_Non_zero=(5, "Transition To Non-zero")
)
compressALG = create_menu(
    "compressALG",
    N_to_1_Low_Value=(0, "N to 1 Low Value"),
    N_to_1_High_Value=(1, "N to 1 High Value"),
    N_to_1_Average=(2, "N to 1 Average"),
    Average=(3, "Average"),
    Circular_Buffer=(4, "Circular Buffer"),
    N_to_1_Median=(5, "N to 1 Median")
)
dfanoutSELM = create_menu(
    "dfanoutSELM",
    All=(0, "All"),
    Specified=(1, "Specified"),
    Mask=(2, "Mask")
)
fanoutSELM = create_menu(
    "fanoutSELM",
    All=(0, "All"),
    Specified=(1, "Specified"),
    Mask=(2, "Mask")
)
gpibACMD = create_menu(
    "gpibACMD",
    none=(0, "None"),
    Group_Execute_Trig___GET=(1, "Group Execute Trig. (GET)"),
    Go_To_Local__GTL=(2, "Go To Local (GTL)"),
    Selected_Dev__Clear__SDC=(3, "Selected Dev. Clear (SDC)"),
    Take_Control__TCT=(4, "Take Control (TCT)"),
    Serial_Poll=(5, "Serial Poll")
)
gpibUCMD = create_menu(
    "gpibUCMD",
    none=(0, "None"),
    Device_Clear__DCL=(1, "Device Clear (DCL)"),
    Local_Lockout__LL0=(2, "Local Lockout (LL0)"),
    Serial_Poll_Disable__SPD=(3, "Serial Poll Disable (SPD)"),
    Serial_Poll_Enable__SPE=(4, "Serial Poll Enable (SPE)"),
    Unlisten__UNL=(5, "Unlisten (UNL)"),
    Untalk__UNT=(6, "Untalk (UNT)")
)
histogramCMD = create_menu(
    "histogramCMD",
    Read=(0, "Read"),
    Clear=(1, "Clear"),
    Start=(2, "Start"),
    Stop=(3, "Stop")
)
ipDRTO = create_menu(
    "ipDRTO",
    unknown=(0, "Unknown"),
    No=(1, "No"),
    Yes=(2, "Yes")
)
menuAlarmSevr = create_menu(
    "menuAlarmSevr",
    NO_ALARM=(0, "NO_ALARM"),
    MINOR=(1, "MINOR"),
    MAJOR=(2, "MAJOR"),
    INVALID=(3, "INVALID")
)
menuAlarmStat = create_menu(
    "menuAlarmStat",
    NO_ALARM=(0, "NO_ALARM"),
    READ=(1, "READ"),
    WRITE=(2, "WRITE"),
    HIHI=(3, "HIHI"),
    HIGH=(4, "HIGH"),
    LOLO=(5, "LOLO"),
    LOW=(6, "LOW"),
    STATE=(7, "STATE"),
    COS=(8, "COS"),
    COMM=(9, "COMM"),
    TIMEOUT=(10, "TIMEOUT"),
    HWLIMIT=(11, "HWLIMIT"),
    CALC=(12, "CALC"),
    SCAN=(13, "SCAN"),
    LINK=(14, "LINK"),
    SOFT=(15, "SOFT"),
    BAD_SUB=(16, "BAD_SUB"),
    UDF=(17, "UDF"),
    DISABLE=(18, "DISABLE"),
    SIMM=(19, "SIMM"),
    READ_ACCESS=(20, "READ_ACCESS"),
    WRITE_ACCESS=(21, "WRITE_ACCESS")
)
menuConvert = create_menu(
    "menuConvert",
    NO_CONVERSION=(0, "NO CONVERSION"),
    SLOPE=(1, "SLOPE"),
    LINEAR=(2, "LINEAR"),
    typeKdegF=(3, "typeKdegF"),
    typeKdegC=(4, "typeKdegC"),
    typeJdegF=(5, "typeJdegF"),
    typeJdegC=(6, "typeJdegC"),
    typeEdegF=(7, "typeEdegF(ixe only)"),
    typeEdegC=(8, "typeEdegC(ixe only)"),
    typeTdegF=(9, "typeTdegF"),
    typeTdegC=(10, "typeTdegC"),
    typeRdegF=(11, "typeRdegF"),
    typeRdegC=(12, "typeRdegC"),
    typeSdegF=(13, "typeSdegF"),
    typeSdegC=(14, "typeSdegC")
)
menuFtype = create_menu(
    "menuFtype",
    STRING=(0, "STRING"),
    CHAR=(1, "CHAR"),
    UCHAR=(2, "UCHAR"),
    SHORT=(3, "SHORT"),
    USHORT=(4, "USHORT"),
    LONG=(5, "LONG"),
    ULONG=(6, "ULONG"),
    INT64=(7, "INT64"),
    UINT64=(8, "UINT64"),
    FLOAT=(9, "FLOAT"),
    DOUBLE=(10, "DOUBLE"),
    ENUM=(11, "ENUM")
)
menuIvoa = create_menu(
    "menuIvoa",
    Continue_normally=(0, "Continue normally"),
    Don_t_drive_outputs=(1, "Don't drive outputs"),
    Set_output_to_IVOV=(2, "Set output to IVOV")
)
menuOmsl = create_menu(
    "menuOmsl",
    supervisory=(0, "supervisory"),
    closed_loop=(1, "closed_loop")
)
menuPini = create_menu(
    "menuPini",
    NO=(0, "NO"),
    YES=(1, "YES"),
    RUN=(2, "RUN"),
    RUNNING=(3, "RUNNING"),
    PAUSE=(4, "PAUSE"),
    PAUSED=(5, "PAUSED")
)
menuPost = create_menu(
    "menuPost",
    OnChange=(0, "On Change"),
    Always=(1, "Always")
)
menuPriority = create_menu(
    "menuPriority",
    LOW=(0, "LOW"),
    MEDIUM=(1, "MEDIUM"),
    HIGH=(2, "HIGH")
)
menuScan = create_menu(
    "menuScan",
    Passive=(0, "Passive"),
    Event=(1, "Event"),
    I_O_Intr=(2, "I/O Intr"),
    scan_10_second=(3, "10 second"),
    scan_5_second=(4, "5 second"),
    scan_2_second=(5, "2 second"),
    scan_1_second=(6, "1 second"),
    scan_point_5_second=(7, ".5 second"),
    scan_point_2_second=(8, ".2 second"),
    scan_point_1_second=(9, ".1 second")
)
menuSimm = create_menu(
    "menuSimm",
    NO=(0, "NO"),
    YES=(1, "YES"),
    RAW=(2, "RAW")
)
menuYesNo = create_menu(
    "menuYesNo",
    NO=(0, "NO"),
    YES=(1, "YES")
)
motorDIR = create_menu(
    "motorDIR",
    Pos=(0, "Pos"),
    Neg=(1, "Neg")
)
motorFOFF = create_menu(
    "motorFOFF",
    Variable=(0, "Variable"),
    Frozen=(1, "Frozen")
)
motorMODE = create_menu(
    "motorMODE",
    Position=(0, "Position"),
    Velocity=(1, "Velocity")
)
motorRMOD = create_menu(
    "motorRMOD",
    D=(0, "Default"),  # noqa
    A=(1, "Arithmetic"),  # noqa
    G=(2, "Geometric"),  # noqa
    I=(3, "In-Position")  # noqa
)
motorSET = create_menu(
    "motorSET",
    Use=(0, "Use"),
    Set=(1, "Set")
)
motorSPMG = create_menu(
    "motorSPMG",
    Stop=(0, "Stop"),
    Pause=(1, "Pause"),
    Move=(2, "Move"),
    Go=(3, "Go")
)
motorSTUP = create_menu(
    "motorSTUP",
    OFF=(0, "OFF"),
    ON=(1, "ON"),
    BUSY=(2, "BUSY")
)
motorTORQ = create_menu(
    "motorTORQ",
    Disable=(0, "Disable"),
    Enable=(1, "Enable")
)
motorUEIP = create_menu(
    "motorUEIP",
    No=(0, "No"),
    Yes=(1, "Yes")
)
selSELM = create_menu(
    "selSELM",
    Specified=(0, "Specified"),
    High_Signal=(1, "High Signal"),
    Low_Signal=(2, "Low Signal"),
    Median_Signal=(3, "Median Signal")
)
seqSELM = create_menu(
    "seqSELM",
    All=(0, "All"),
    Specified=(1, "Specified"),
    Mask=(2, "Mask")
)
serialBAUD = create_menu(
    "serialBAUD",
    unknown=(0, "Unknown"),
    choice_300=(1, "300"),
    choice_600=(2, "600"),
    choice_1200=(3, "1200"),
    choice_2400=(4, "2400"),
    choice_4800=(5, "4800"),
    choice_9600=(6, "9600"),
    choice_19200=(7, "19200"),
    choice_38400=(8, "38400"),
    choice_57600=(9, "57600"),
    choice_115200=(10, "115200"),
    choice_230400=(11, "230400"),
    choice_460800=(12, "460800"),
    choice_576000=(13, "576000"),
    choice_921600=(14, "921600"),
    choice_1152000=(15, "1152000")
)
serialDBIT = create_menu(
    "serialDBIT",
    unknown=(0, "Unknown"),
    choice_5=(1, "5"),
    choice_6=(2, "6"),
    choice_7=(3, "7"),
    choice_8=(4, "8")
)
serialFCTL = create_menu(
    "serialFCTL",
    unknown=(0, "Unknown"),
    none=(1, "None"),
    Hardware=(2, "Hardware")
)
serialIX = create_menu(
    "serialIX",
    unknown=(0, "Unknown"),
    No=(1, "No"),
    Yes=(2, "Yes")
)
serialMCTL = create_menu(
    "serialMCTL",
    unknown=(0, "Unknown"),
    CLOCAL=(1, "CLOCAL"),
    Yes=(2, "YES")
)
serialPRTY = create_menu(
    "serialPRTY",
    unknown=(0, "Unknown"),
    none=(1, "None"),
    Even=(2, "Even"),
    Odd=(3, "Odd")
)
serialSBIT = create_menu(
    "serialSBIT",
    unknown=(0, "Unknown"),
    choice_1=(1, "1"),
    choice_2=(2, "2")
)
stringinPOST = create_menu(
    "stringinPOST",
    OnChange=(0, "On Change"),
    Always=(1, "Always")
)
stringoutPOST = create_menu(
    "stringoutPOST",
    OnChange=(0, "On Change"),
    Always=(1, "Always")
)
waveformPOST = create_menu(
    "waveformPOST",
    Always=(0, "Always"),
    OnChange=(1, "On Change")
)

acalcoutDOPT = NotImplementedMenu
acalcoutINAV = NotImplementedMenu
acalcoutOOPT = NotImplementedMenu
acalcoutSIZE = NotImplementedMenu
acalcoutWAIT = NotImplementedMenu
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
mcaCHAS = NotImplementedMenu
mcaERAS = NotImplementedMenu
mcaMODE = NotImplementedMenu
mcaREAD = NotImplementedMenu
mcaSTRT = NotImplementedMenu
scalcoutDOPT = NotImplementedMenu
scalcoutINAV = NotImplementedMenu
scalcoutOOPT = NotImplementedMenu
scalcoutWAIT = NotImplementedMenu
scalerCNT = NotImplementedMenu
scalerCONT = NotImplementedMenu
scalerD1 = NotImplementedMenu
scalerG1 = NotImplementedMenu
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
