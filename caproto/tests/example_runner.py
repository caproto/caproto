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
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   '..', '..', 'scripts', script)
        print("--------------------------------------")
        print(f"Running {script_path} with coverage")
        sys.argv = sys.argv[2:]
        try:
            runpy.run_path(script_path, run_name='__main__')
        except KeyboardInterrupt:
            print('KeyboardInterrupt received on example_runner; exiting')
        else:
            print(f'{script_path} exited cleanly')
    else:
        print("--------------------------------------")
        print(f"Running {example_module} with coverage")
        print(os.getcwd())
        sys.argv = sys.argv[:1] + sys.argv[2:]
        print(f"sys.argv is now: {sys.argv}")
        try:
            runpy.run_module(example_module, run_name='__main__')
        except KeyboardInterrupt:
            print('KeyboardInterrupt received on example_runner; exiting')
        else:
            print(f'{example_module} exited cleanly')
