#!/usr/bin/env python

assert __name__ == "__main__", "I don't think you want to import this..."

try:
    from setuptools import setup
except:
    from distutils.core import setup


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
author, author_email = ("Oliver Gould", "ver@olix0r.net")


setup(
    name = pkgVer["version"].package.replace(".", "_"),
    version = pkgVer["version"].short(),

    description = "An HTTP 1.1 user agent for the programming web.",
    long_description = getReadme(),
    url = "http://pendrell.olix0r.net/",

    license = "MIT",
    classifiers = [
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Twisted",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Topic :: Internet :: WWW/HTTP",
        ],

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


