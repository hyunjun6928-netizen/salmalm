"""Setuptools hook: bundle JS modules before building."""
import subprocess
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithBundle(build_py):
    def run(self):
        try:
            subprocess.check_call(["python3", "scripts/bundle_js.py"])
        except Exception as e:
            print(f"⚠️ JS bundle skipped: {e}")
        super().run()


setup(cmdclass={"build_py": BuildWithBundle})
