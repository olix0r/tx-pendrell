#!/usr/bin/env python

assert __name__ == "__main__", "I don't think you want to import this..."

from distutils import core


def getReadme(path="README"):
    f = open(path)
    try:
        return f.read()
    finally:
        f.close()


def getVersion():
    import os
    packageSeedFile = os.path.join("lib", "_version.py")
    ns = {}
    execfile(packageSeedFile, ns)
    return ns

pkgVer = getVersion()
author, author_email = pkgVer["author"].rsplit(None, 1)


core.setup(
    name = pkgVer["version"].package.replace(".", "_"),
    version = pkgVer["version"].short(),

    description = "An HTTP 1.1 user agent for the programming web.",
    long_description = getReadme(),
    #url = "http://olix0r.net/py/pendrell",

    packages = ["pendrell", "pendrell.cases", ],
    package_dir = {
        "pendrell": "lib",
        "pendrell.cases": "lib/cases",
        },

    provides = ["pendrell", ],
    requires = ["twisted.web", ],

    author = author,
    author_email = author_email,
    maintainer = author,
    maintainer_email = author_email,
    )


__id__ = """$Id$"""[5:-2]

