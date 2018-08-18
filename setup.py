from setuptools import setup

setup(name='tau',
      version='0.1',
      description='Tau Compiler and JIT REPL',
      author='Daniel Thorngren',
      license='MIT',
      packages=['tau'],
      scripts=['bin/tau'],
      install_requires=[
          'subprocess32',
          'llvmlite',
          'pygments',
          'prompt_toolkit<2.0',
          'ctypes'],
      test_suite="test_tau.TauTester"
      )
