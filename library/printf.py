# printf.py
from __future__ import print_function
import sys

def printf(str, *args):
    print(str % args, end='')
    sys.stdout.flush()
