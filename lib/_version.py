from twisted.python.versions import Version

author = "Oliver V. Gould <pendrell-devel@olix0r.net>"
copyright = """Copyright (c) 2008-2010 Oliver V. Gould.  All rights reserved."""
version = Version("pendrell", 0, 2, 0)

# Don't export t.p.v.Version
del Version

__id__ = "$Id: $"[5:-2]

