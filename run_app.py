import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = open("server_stdout.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
sys.stderr = open("server_stderr.log", "w", encoding="utf-8", buffering=1)  # noqa: SIM115
import runpy

runpy.run_path("app.py", run_name="__main__")
