"""SalmAlm launcher for PyInstaller exe."""
import sys
import os

# Set working directory to exe location
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from salmalm.__main__ import main
main()
