from twisted.python.log import *

from logging import DEBUG, INFO, WARN, ERROR  # for logLevel constants
TRACE = 0


def debug(*args, **kw):
    kw.setdefault("logLevel", DEBUG)
    msg(*args, **kw)


def warn(*args, **kw):
    kw.setdefault("logLevel", WARN)
    msg(*args, **kw)



__id__ = "$Id: $"[5:-2]

