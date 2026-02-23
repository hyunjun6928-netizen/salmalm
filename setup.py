"""Setuptools hook: bundle JS modules before building."""
import os
import subprocess
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithBundle(build_py):
    def run(self):
        try:
            subprocess.check_call(["python3", "scripts/bundle_js.py"])
        except Exception as e:
            if os.environ.get("SALMALM_RELEASE") == "1":
                raise RuntimeError(f"JS bundle failed in release mode: {e}") from e
            print(f"⚠️ JS bundle skipped: {e}")
        # MED-14: pop custom args before setuptools sees them
        import sys
        sys.argv = [a for a in sys.argv if not a.startswith("--salmalm-")]
        super().run()


setup(cmdclass={"build_py": BuildWithBundle})
