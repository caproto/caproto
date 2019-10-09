# for testing compliance to a real ai record
# used with "test_ai_compliance.py"
from caproto.server import ioc_arg_parser, run
from caproto.server import pvproperty, PVGroup


class testAIrec(PVGroup):
    def __init__(self,  prefix, **kwargs):
        super().__init__(prefix, **kwargs)
        print("init")
        pv_name="TEST_PV:ai_test"
        new_pv = mock_ai_record(prefix=f'{pv_name}')
        self.pvdb.update(new_pv.pvdb)
        print(f"adding to db: {pv_name}")  # our pv_name is the prefix.


# Make a class to template Status Pvs, based on PVGroup. Give an intial value that is a float.
class mock_ai_record(PVGroup):
    readback=pvproperty(value=0.1, mock_record='ai', name='', read_only=True) # Look in server.py in PVSpec class def for parameters #use this if you want PV name=parmName


def main():
    ioc_options, run_options = ioc_arg_parser(
        default_prefix='TEST_PV:',
        desc='IOC using CAPROTO')
    print("ioc_options" + str(ioc_options))

    ioc = testAIrec(**ioc_options)  
    
    print("ioc._pvs_" + str(ioc._pvs_))

    run_options['log_pv_names'] = True  # does same as command line --list-pvs
    print("run_options:" + str(run_options))
    run(ioc.pvdb, **run_options)  # blocking

    print("end")


if __name__ == '__main__':
    main()
