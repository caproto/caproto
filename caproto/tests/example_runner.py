import os
import coverage
import sys
import runpy


if __name__ == '__main__':
    cov = coverage.process_startup()

    cov._warn_no_data = True
    print({env: val
           for env, val in os.environ.items()
           if 'COVERAGE' in env})

    example_module = sys.argv[1]
    print("--------------------------------------")
    print(f"Running {example_module} with coverage")
    print(os.getcwd())
    sys.argv = sys.argv[:1] + sys.argv[2:]
    print(f"sys.argv is now: {sys.argv}")
    try:
        runpy.run_module(example_module, run_name='__main__')
    except KeyboardInterrupt:
        print('KeyboardInterrupt received on example_runner; exiting')
