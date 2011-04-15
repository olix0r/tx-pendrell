try:
  from twisted.python.versions import Version

except ImportError:
  class Version(object):
    def __init__(self, package, major, minor, nano, pre=None):
      self.package = package
      self.major = major
      self.minor = minor
      self.nano = nano
      self.pre = pre

    def short(self):
      fmt = "{0.major}.{0.minor}.{0.nano}"
      if self.pre:
        fmt += "pre{0.pre}"
      return fmt.format(self)


copyright = """Copyright (c) 2008-2010 Oliver V. Gould.  All rights reserved."""
version = Version("pendrell", 0, 3, 8)

# Don't export t.p.v.Version
del Version

