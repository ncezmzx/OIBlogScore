"""UTF-8 console output for tools on legacy Windows code pages."""
import sys


def utf8_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except (AttributeError, OSError):
            pass
