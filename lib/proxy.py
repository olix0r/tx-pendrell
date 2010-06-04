#!/usr/bin/env python2.5

"""Proxies to the Programming Web.

Proxy instances provide the IRequester interface, and therefore be triggered
with an instance of Request.  The Reuqester interface should provide all 

Proxy instances are installed into the Agent.  The Agent, or a subclass thereof,
should provide foxyproxy-like support to only provide proxied

TODO
- SOCKS 5 
"""


from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import failure

from pendrell import log
from pendrell.protocols import (
        HTTPProtocol,
        SOCKSv4ClientProtocol,
        SOCKSv4aClientProtocol)
from pendrell.requester import RequesterBase



class Proxy(RequesterBase):


    def __init__(self, *args, **kw):
        self.user = kw.pop("user", None)
        self.password = kw.pop("password", None)
        RequesterBase.__init__(self, *args, **kw)

        self.remoteHost, self.remotePort = None, None
        self._responseQueue = list()


    def setRemote(self, host, port):
        self.remoteHost = host
        self.remotePort = int(port)

    
    def buildProtocol(self, addr):
        protocol = RequesterBase.buildProtocol(self, addr)
        protocol.remoteHost = self.remoteHost
        protocol.remotePort = self.remotePort

        return protocol



class HTTPProxy(Proxy):

    def __init__(self, *args, **kw):
        pass



class HTTPProxyProtocol(HTTPProtocol):

    def sendCommand(self, request):
        command = "%s %s HTTP/1.1%s" % (request.method, request.url, CRLF)
        log.msg("sending: %r" % command, logLevel=log.TRACE)
        self.transport.write(command)



class SOCKSProxyProtocolBase(object):

    socksClass = None
    appClass = None


    def __init__(self):
        self.socksClass.__init__(self)
        self.appClass.__init__(self)

        self._tunneled = False


    @inlineCallbacks
    def connectionMade(self):
        yield self.socksClass.connectionMade(self)
        self.appClass.connectionMade(self)


    def connectionLost(self, reason):
        self._tunneled = False

        self.appClass.connectionLost(self, reason)
        self.socksClass.connectionLost(self, reason)


    @inlineCallbacks
    def connectionMade(self):
        yield self.socksClass.connectionMade(self)
        self.appClass.connectionMade(self)


    @inlineCallbacks
    def openConnection(self, server, port, user=""):
        log.msg("Opening SOCKS-tunnel to %s:%d" % (server, port))
        conn = yield self.socksClass.openConnection(self, server, port, user)
        log.msg("socks connected: %s:%d" % (server, port))

        self._tunneled = True

        returnValue(conn)


    def dataReceived(self, data):
        if not self._tunneled:
            klass = self.socksClass
        else:
            klass = self.appClass

        return klass.dataReceived(self, data)



class SOCKSv4HTTPRequester(SOCKSProxyProtocolBase,
        SOCKSv4ClientProtocol, HTTPProtocol):
    socksClass = SOCKSv4ClientProtocol
    appClass = HTTPProtocol


class SOCKSv4aHTTPRequester(SOCKSProxyProtocolBase,
        SOCKSv4aClientProtocol, HTTPProtocol):
    socksClass = SOCKSv4aClientProtocol
    appClass = HTTPProtocol


class SOCKSv4Proxy(Proxy):
    protocol = SOCKSv4HTTPRequester

class SOCKSv4aProxy(Proxy):
    protocol = SOCKSv4aHTTPRequester



class Proxyer(object):

    def __init__(self, proxy=None):
        self.proxy = proxy

    def getRequester(self, request):
        # XXX Support timeout
        assert self.proxy is None or isinstance(self.proxy, Proxy)
        return self.proxy  # may be None, clearly.


__id__ = "$Id: $"[5:-2]

