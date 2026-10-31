"""Import this first in a test: it puts <repo>/src at the front of sys.path."""
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if sys.path[:1] != [SRC]:
    sys.path.insert(0, SRC)
