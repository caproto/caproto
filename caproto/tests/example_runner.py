import os
import coverage
import sys
import runpy


if __name__ == '__main__':
    cov = coverage.process_startup()
    if cov is not None:
        cov._warn_no_data = True
    print({env: val
           for env, val in os.environ.items()
           if 'COVERAGE' in env})

    example_module = sys.argv[1]

    if example_module == '--script':
        script = sys.argv[2]
        from caproto.commandline.get import main as get_cli
        from caproto.commandline.put import main as put_cli
        from caproto.commandline.monitor import main as monitor_cli
        from caproto.commandline.repeater import main as repeater_cli
        entry_point = {'caproto-get': get_cli,
                       'caproto-put': put_cli,
                       'caproto-monitor': monitor_cli,
                       'caproto-repeater': repeater_cli,
                       }[script]
        print("--------------------------------------")
        print(f"Running {script} with coverage")
        sys.argv = sys.argv[2:]
        print(f"Arguments: {sys.argv}")
        try:
            entry_point()
        except KeyboardInterrupt:
            print('KeyboardInterrupt received on example_runner; exiting')
        else:
            print(f'{script} exited cleanly')
    else:
        print("--------------------------------------")
        print(f"Running {example_module} with coverage")
        print(os.getcwd())
        sys.argv = sys.argv[:1] + sys.argv[2:]
        print(f"Arguments: {sys.argv}")
        try:
            runpy.run_module(example_module, run_name='__main__')
        except KeyboardInterrupt:
            print('KeyboardInterrupt received on example_runner; exiting')
        else:
            print(f'{example_module} exited cleanly')
