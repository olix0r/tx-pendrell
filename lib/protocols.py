from struct import calcsize, pack, unpack, error as UnpackError

from socket import inet_aton, inet_ntoa
from urlparse import urlunsplit

from twisted.internet import (error as netErr,
        interfaces as netInterfaces, protocol, reactor)
from twisted.internet.defer import Deferred, inlineCallbacks, returnValue
from twisted.protocols import basic, policies
from twisted.python.failure import Failure
from twisted.web import http

from pendrell import log
from pendrell.decoders import ChunkingIncrementalDecoder, getIncrementalDecoder
from pendrell.error import (IncompleteResponse, RedirectedResponse,
        ResponseTimeout, RetryResponse, UnauthorizedResponse, WebError,
        FailableMixin)
from pendrell.util import URLPath, CRLF


OKAY_CODES= range(200, 300)
NO_BODY_CODES = http.NO_BODY_CODES
REDIRECT_CODES = (
        http.MOVED_PERMANENTLY,
        http.SEE_OTHER,
        http.FOUND,
        http.TEMPORARY_REDIRECT,
    )
RETRY_CODES= (
        http.SERVICE_UNAVAILABLE,
    )
UNAUTHORIZED_CODES = (
        http.UNAUTHORIZED,
    )



class HTTPProtocol(basic.LineReceiver, policies.TimeoutMixin):
    """Represents an HTTP channel.
    """

    def __init__(self):
        self._pendingResponses = list()

        self.timedOut = False

        self._contentLength = None
        self._contentSize = None

        self._chunkDecoder = None


    def __repr__(self):
        netLoc = "%s://%s:%d" % (self.scheme, self.host, self.port)
        return "<%s: %s>" % (self.__class__.__name__, netLoc)

    
    @property
    def _currentResponse(self):
        return self._pendingResponses[0]


    def connectionMade(self):
        self._connected = True
        basic.LineReceiver.connectionMade(self)
        self.sendRequests()


    def connectionLost(self, reason):
        self._connected = False
        return basic.LineReceiver.connectionLost(self, reason)


    def timeoutConnection(self):
        #log.debug("%r: connection timeout" % self)
        self.timedOut = True
        return policies.TimeoutMixin.timeoutConnection(self)


    @inlineCallbacks
    def sendRequests(self):
        connected = True

        while connected:
            try:
                request = yield self.factory.getNextRequest()
                self.sendRequest(request)

            except (netErr.ConnectionLost, netErr.ConnectionDone) :
                connected = False

        while self._pendingResponses:
            self.handleResponseEnd()


    #
    # HTTP requesting methods 
    #

    def sendRequest(self, request):
        """Perform the given HTTP request."""
        request.prepareHeaders()

        #log.debug("Sending request" % request)
        self.sendCommand(request)
        self.sendHeaders(request)
        self.sendContent(request)

        response = request.buildResponse()
        self._pendingResponses.append(response)


    def _urlToRequestString(self, url):
        return urlunsplit((None, None, url.path, url.query, None))


    def sendCommand(self, request):
        path = self._urlToRequestString(request.url)
        command = "%s %s HTTP/1.1%s" % (request.method, path, CRLF)
        self.transport.write(command)


    def sendHeaders(self, request):
        for name, value in request.headers.iteritems():
            header = "%s: %s%s" % (name, value, CRLF)
            self.transport.write(header)
        self.transport.write(CRLF)    

    
    def sendContent(self, request):
        content = request.data
        if content:
            self.transport.write(content)


    #
    # HTTP Headers received as lines
    #

    def lineReceived(self, line):
        assert self._pendingResponses

        if line == "":
            self.handleEndHeaders()

            if self._currentResponseHasContent():
                self.setRawMode()

            else:
                self.handleResponseEnd()

        elif not self._currentResponse.hasStatus:
            self._parseStatusMessage(line)

        else:
            self._parseHeader(line)


    def _parseStatusMessage(self, line):
        info = line.split(None, 2)
        if len(info) == 3:
            version, status, message = info
        else:
            version, status = info
            message = ""

        self.handleStatus(version, status, message)


    def _parseHeader(self, header):
        key, val = header.split(": ", 1)
        self.handleHeader(key, val)


    def _loadDecoders(self):
        self._chunkDecoder = None
        self._genericDecoders = list()

        encodingHeaders = self._currentResponse.headers.get("transfer-encoding")
        if encodingHeaders:
            encodings = encodingHeaders[0].split(",")

            for encoding in encodings:
                decoderClass = getIncrementalDecoder(encoding)
                if decoderClass:
                    if encoding == "chunked":
                        self._chunkDecoder = decoderClass()
                    else:
                        self._genericDecoders.append(decoderClass())


    def _decodeData(self, data):
        assert data is not None

        for decoder in self._genericDecoders:
            data = decoder.decode(data)

        return data


    def _determineContentLength(self):
        if "content-length" in self._currentResponse.headers:
            length = self._currentResponse.headers["content-length"][-1]
            self._contentLength = int(length)


    def _currentResponseHasContent(self):
        return not (self._currentResponse.status in NO_BODY_CODES
                or self._currentResponse.request.method == "HEAD"
                or self._contentLength == 0)


    #
    # HTTP Content received as raw data
    #

    def setRawMode(self):
        basic.LineReceiver.setRawMode(self)
        self._contentSize = 0


    def rawDataReceived(self, raw):
        content, final, raw = self._processContent(raw)

        self.handleContent(content)

        assert not (raw and not final)
        if final:
            self.handleResponseEnd()

            if raw:
                self.dataReceived(raw)


    def _processContent(self, raw):
        if self._chunkDecoder:
            data = self._chunkDecoder.decode(raw)
            final = self._chunkDecoder.finished
            if final:
                raw = self._chunkDecoder.getExtra()
                self._chunkDecoder = None
            else:
                raw = ""

            content = self._decodeData(data)
            self._contentSize += len(content)

        else:
            assert self._contentSize is not None
            if self._contentLength is not None:
                assert 0 <= self._contentSize <= self._contentLength, \
                        "Content size (%d) is greater than content length (%d)" % \
                        (self._contentSize, self._contentLength)

                if self._contentSize + len(raw) > self._contentLength:
                    dataLen = self._contentLength - self._contentSize
                    data, raw = raw[:dataLen], raw[dataLen:]
                else:
                    data, raw = raw, ""
            else:
                data, raw = raw, ""

            self._contentSize += len(data)
            content = self._decodeData(data)

            if self._contentLength is not None:
                final = bool(self._contentSize == self._contentLength)
            else:
                final = False

        return (content, final, raw)


    #
    # Handle the response as it is parsed
    #

    def handleStatus(self, version, status, message):
        """Initial response."""
        self._currentResponse.gotStatus(version, status, message)


    def handleHeader(self, key, value):
        self._currentResponse.gotHeader(key, value)


    def handleEndHeaders(self):
        self._determineContentLength()
        self._loadDecoders()


    def handleContent(self, data):
        self._currentResponse.dataReceived(data)


    def handleResponseEnd(self):
        response = self._pendingResponses.pop(0)
        response.done()

        self.handleResponse(response)
        self.setLineMode()


    def handleResponse(self, response):
        # Done processing the current request
        #logFmt = "%r: %s: handling %%s response %r [%d]" % (
        #         self, response.request, response, len(response))

        if self.timedOut:
            #log.debug(logFmt % "timed-out")
            response.status = http.REQUEST_TIMEOUT
            responseValue = ResponseTimeout.Failure(response, self.timeOut)

        elif response.status in REDIRECT_CODES:
            # Response redirected
            #log.debug(logFmt % "redirect")
            responseValue = RedirectedResponse.Failure(response)

        elif response.status in RETRY_CODES:
            # Response redirected
            #log.debug(logFmt % "redirect")
            responseValue = RetryResponse.Failure(response)

        elif response.status in UNAUTHORIZED_CODES:
            # Response unauthorized
            #log.debug(logFmt % "unauthorized")
            responseValue = UnauthorizedResponse.Failure(response)

        elif response.status in OKAY_CODES:
            # SUCCESS
            #log.debug(logFmt % "success")
            responseValue = response

        else:
            # Generic failure
            #log.debug(logFmt % "failure")
            responseValue = WebError.Failure(response)

        reactor.callLater(0, response.request.response.callback, responseValue)



class SOCKSv4ClientProtocol(protocol.Protocol):
    """SOCKSv4 Client Protocol
    
    TODO support binding also.
    """

    _VERSION_CODE = 0x04

    _CONNECT_CODE = 0x01
    _BIND_CODE = 0x02

    _REQUEST_GRANTED_CODE = 0x5a
    _REQUEST_REJECTED_CODE = 0x5b
    _REQUEST_REJECTED_IDENTD_CODE = 0x5c
    _REQUEST_REJECTED_USER_CODE = 0x5d

    def __init__(self):
        self.__tunnel = None

        self.remoteHost = None
        self.remotePort = None
        self.user = ""


    def connectionMade(self):
        assert None not in (self.remoteHost, self.remotePort)
        return self.openConnection(self.remoteHost, self.remotePort, self.user)



    @inlineCallbacks
    def openConnection(self, host, port, user=""):
        hostIP = yield reactor.resolve(host)
        server = inet_aton(hostIP)

        packed = pack("!BBH", self._VERSION_CODE, self._CONNECT_CODE, port)
        packed += inet_aton(hostIP)
        packed += user + "\000"

        self.transport.write(packed)
        remote = yield self.__waitForTunnel()

        returnValue(remote)


    def __waitForTunnel(self):
        if not self.__tunnel:
            self.__tunnel = Deferred()

        return self.__tunnel


    # XXX IPv4-Specific
    def dataReceived(self, data):
        (version, status, server, port) = self._parseData(data)

        if status == self._REQUEST_GRANTED_CODE:
            self.__tunnel.callback((server, port, self.transport))

        else:
            if status == self._REQUEST_REJECTED_CODE:
                err = SOCKSRejected(server, port)
            elif status == self._REQUEST_REJECTED_IDENTD_CODE:
                err = SOCKSIdentdRejected(server, port)
            elif status == self._REQUEST_REJECTED_USER_CODE:
                err = SOCKSUserRejected(server, port)

            self.__tunnel.errback(Failure(err))

        self.__tunnel = None


    def _parseData(self, data):
        replyFmt = "!BBH"
        dataLen = len(data)

        replyLen = calcsize(replyFmt) + 4
        if dataLen != replyLen:
            raise ValueError("data (%r) is not %d bytes" % (data, replyLen))
        (version, status, port) = unpack(replyFmt, data[:4])

        packedServer = data[4:]
        server = inet_ntoa(packedServer)

        return (version, status, server, port)



class SOCKSv4aClientProtocol(SOCKSv4ClientProtocol):
    """SOCKSv4a Client Protocol

    UNTESTED
    """

    _INVALID_SERVER = "0.0.0.1"

    def openConnection(self, host, port, user=""):
        """Allows the proxy to perform DNS lookup.
        """
        version = self._VERSION_CODE
        command = self._CONNECT_CODE
        server = inet_aton(self._INVALID_SERVER)
        domain = host

        packed = pack("!BBH", version, command, port) \
               + server \
               + user + "\000" \
               + host + "\000"
        self.transport.write(packed)

        return self.__waitForTunnel()



#
# SOCKS Errors
#

class SOCKSRejected(Exception, FailableMixin):

    message = "SOCKS request rejected"

    def __init__(self, server, port):
        Exception.__init__(self, self.message, server, port)


class SOCKSIdentdRejected(SOCKSRejected):
    message = "SOCKS request rejected because the server " + \
              "cannot connect to identd on the client.",


class SOCKSUserRejected(SOCKSRejected):
    message = "SOCKS request because the client program and " + \
              "identd report different user-ids."


__id__ = "$Id: $"[5:-2]

