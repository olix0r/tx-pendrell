# Copyright (c) 2008-2010 Oliver Gould.
# All rights reserved.

"""
Pendrell: A Twisted HTTP/1.1 User Agent for the Programmatic Web.
"""

from pendrell._version import copyright, version
from pendrell.agent import Agent, getPage, downloadPage

__copyright__ = copyright
__version__ = version.short()
