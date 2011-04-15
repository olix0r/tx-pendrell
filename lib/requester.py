from twisted.internet import reactor
from twisted.internet.defer import (
        Deferred, DeferredList, succeed,
        inlineCallbacks, returnValue)
from twisted.internet.interfaces import IProtocolFactory
from twisted.internet.error import ConnectionDone

from twisted.internet.protocol import ClientFactory as _ClientFactory
from zope.interface import Attribute, Interface, implements

from pendrell.protocols import HTTPProtocol



class IRequester(IProtocolFactory):

    scheme = Attribute("URL scheme")
    host = Attribute("Remote host (may be None for some schemes)")
    port = Attribute("Remote port (may be None for some schemes)")

    secure = Attribute("True iff this scheme provides secure communication.")

    maxConnections = Attribute("Maximum number of concurrent connections")

    def issueRequest(request):
        """Issue a request (duh)."""



class Multiplexer(object):
    implements(IRequester)

    maxConnections = 2
    timeout = None

    def __init__(self, requesterClass, scheme, host, port, **kw):
        self.requesterClass = requesterClass
        self._requesters = list()

        self.scheme = scheme
        self.host = host
        self.port = port

        self.maxConnections = kw.pop("maxConnections", self.maxConnections)
        self.timeout = kw.pop("timeout", self.timeout)


    @property
    def secure(self):
        return self.requesterClass.secure


    def __str__(self):
        return "%s://%s:%d" % (self.scheme, self.host, self.port)

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, str(self))


    def buildRequester(self):
        return self.requesterClass(self.scheme, self.host, self.port,
                timeout=self.timeout)


    def getAvailableRequesters(self):
        return [r for r in self._requesters if not r.active]


    @inlineCallbacks
    def issueRequest(self, request):
        requester = yield self._waitForAvailableRequester()
        response = yield requester.issueRequest(request)
        returnValue(response)


    @inlineCallbacks
    def _waitForAvailableRequester(self):
        available = self.getAvailableRequesters()
        if available:
            requester = available[0]

        elif (self.maxConnections is None
                or len(self._requesters) < self.maxConnections):
            requester = self.buildRequester()
            self._requesters.append(requester)

        else:
            assert (self.maxConnections is None 
                    or len(self._requesters) == self.maxConnections)
            requester, idx = yield DeferredList(
                [r.waitForAvailability() for r in self._requesters],
                fireOnOneCallback=True)

        returnValue(requester)


    def loseConnection(self):
        return DeferredList([
            r.loseConnection() for r in self._requesters
            ])



class RequesterBase(_ClientFactory):

    noisy = False
    secure = False

    def __init__(self, scheme, host, port, timeout=None):
        self.scheme = scheme
        self.host, self.port = host, int(port)

        self._availability = None
        self._requestQueue = list()  # Queue of unissued requests
        self._nextRequest = None
        self._pendingResponseCount = 0

        self._connector = None
        self._connectionLost = None

        self.timeout = timeout


    def __str__(self):
        return "%s://%s:%d" % (self.scheme, self.host, self.port)

    def __repr__(self):
        return "<%s: %s: %s>" % (self.__class__.__name__, id(self), str(self))


    @property
    def active(self):
        return bool(self._pendingResponseCount or self._requestQueue)


    @inlineCallbacks
    def issueRequest(self, request):
        assert self._nextRequest is None or len(self._requestQueue) == 0

        # Buffer requests until the connection is made.  Once connected,
        # send requests to the server.
        self._requestQueue.append(request)

        # Otherwise, queue the request and initiate a connection.
        # Once the connection is complete, the protocol will call
        # getNextRequest() and dequeue it.
        if self.disconnected:
            self.connect()

        # If a connected protocol is waiting for a request, issue it
        # (after the execution chain terminates).
        if self._nextRequest:
            reactor.callLater(0, self._nextRequest.callback, request)
            self._nextRequest = None

        response = yield request.response

        returnValue(response)


    @property
    def disconnected(self):
        return bool(self._connector is None
                or self._connector.state == "disconnected")


    @inlineCallbacks
    def getNextRequest(self):
        if len(self._requestQueue) == 0:
            yield self._waitForRequest()

        request = self._requestQueue.pop(0)

        self._watchResponseFor(request)

        returnValue(request)


    def _waitForRequest(self):
        assert len(self._requestQueue) == 0

        if self._nextRequest is None:
            self._nextRequest = Deferred()

        return self._nextRequest


    @inlineCallbacks
    def _watchResponseFor(self, request):
        assert self._pendingResponseCount >= 0

        self._pendingResponseCount += 1
        try:
            response = yield request.response

        finally:
            assert self._pendingResponseCount > 0
            self._pendingResponseCount -= 1

            if not self.active:
                if self._availability is not None:
                    a, self._availability = self._availability, None
                    reactor.callLater(0, a.callback, self)

        returnValue(response)

    def waitForAvailability(self):
        if self._availability is not None:
            d = self._availability
        elif not self.active:
            d = succeed(self)
        else:
            d = self._availability = Deferred()
        return d


    def connect(self):
        assert self.disconnected
        return reactor.connectTCP(self.host, self.port, self, timeout=self.timeout)


    def buildProtocol(self, addr):
        proto = _ClientFactory.buildProtocol(self, addr)

        proto.scheme = self.scheme
        proto.host = self.host
        proto.port = self.port

        if self.timeout is not None:
            proto.setTimeout(self.timeout)

        return proto


    def startedConnecting(self, connector):
        self._connector = connector


    def clientConnectionLost(self, connector, reason):
        """Called when an established connection is lost."""
        if self._connectionLost:
            self._connectionLost.callback(True)
            self._connectionLost = None

        if self._nextRequest:
            self._nextRequest.errback(reason)
            self._nextRequest = None

        if reason.check(ConnectionDone):
            self._reconnectIfRequestsQueued(connector)
        else:
            self._failQueuedRequests(reason)


    def clientConnectionFailed(self, connector, reason):
        assert self._nextRequest is None

        #self._reconnectIfRequestsQueued(connector)
        self._failQueuedRequests(reason)


    def loseConnection(self):
        if not self.disconnected:
            self._connector.disconnect()
            d = self._connectionLost = Deferred()
        else:
            d = succeed(True)
        return d


    def _failQueuedRequests(self, reason):
        while self._requestQueue:
            self._requestQueue.pop(0).response.errback(reason)


    def _reconnectIfRequestsQueued(self, connector):
        # TODO Limit number of retries
        count = len(self._requestQueue)
        if count > 0:
            connector.connect()



class HTTPRequester(RequesterBase):
    """Issues requests to server and builds responses."""

    protocol = HTTPProtocol

    def __init__(self, scheme, host, port, **kw):
        if not scheme.startswith("http"):
            log.warn("Unexpected URL scheme: %s" % scheme)
        RequesterBase.__init__(self, scheme, host, port, **kw)




class HTTPSRequester(HTTPRequester):

    secure = True

    def __init__(self, *args, **kw):
        HTTPRequester.__init__(self, *args, **kw)

        if not self.scheme == "https":
            log.warn("Unexpected URL scheme: %s" % scheme)
        from twisted.internet import ssl

        # XXX AFAIK this does nothing to handle trusted CAs
        self._context =  ssl.ClientContextFactory()


    def connect(self):
        log.debug("Connecting over SSL to %s:%s" % (self.host, self.port))
        reactor.connectSSL(self.host, self.port, self, self._context)



