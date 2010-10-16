from base64 import b64encode
from hashlib import md5
import os
from urllib2 import Request as urllib2_Request

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from twisted.internet import defer
from twisted.python import util

from pendrell.decoders import loadDecoders
from pendrell.error import MD5Mismatch
from pendrell.proxy import Proxy
from pendrell.util import URLPath



class Message(object):

    def __init__(self, url, method="GET", headers=None):
        if not isinstance(url, URLPath):
            url = URLPath.fromString(str(url))
        self._url = url

        self.method = method
        self.headers = util.InsensitiveDict(headers or dict())


    @property
    def scheme(self):
        return self._url.scheme or ""

    @property
    def host(self):
        return self._url.host or ""

    @property
    def port(self):
        return self._url.port or 0

    @property
    def path(self):
        return self._url.path or ""


    def __len__(self):
        return len(getattr(self, "data", ""))


    url = property(
            lambda self: self._url,
            lambda self, url: self.setURL(url),
        )
    def setURL(self, url):
        self._url = URLPath.fromString(url)

    def __str__(self):
        return "%s" % self.url

    def __repr__(self):
        return "<%s: %s: %s>" % (self.__class__.__name__, self.method, self.url)



class Response(Message):

    def __init__(self, request, url, method="GET", headers=None, **kw):
        assert isinstance(request, Request)
        Message.__init__(self, url, method=method, headers=headers)

        assert isinstance(request, Message), "%r is not a Message" % request
        self.request = request

        self.version = kw.get("version")
        self.status = kw.get("status")
        self.message = kw.get("message")
        self._dataLength = long()

        self.timedOut = False

        self.contentDecoders = list()

        self.contentMD5 = md5()


    @classmethod
    def fromResponse(klass, response, **kwArgs):
        from copy import deepcopy
        kw = dict(
                request = response.request,
                url = str(response.url),
                method = response.method,
                headers = deepcopy(response.headers),
                version = response.version,
                status = response.status,
                message = response.message,
            )
        kw.update(kwArgs)
        request = kw.pop("request")
        url = kw.pop("url")
        return klass(request, url, **kw)


    def copy(self, **kwArgs):
        self.fromResponse(self, **kwArgs)


    def __len__(self):
        return self._dataLength


    def __repr__(self):
        status = getattr(self, "status", None) or ""
        url = getattr(self, "url", None) or ""
    
        repr = "%s" % self.__class__.__name__
        if url:
            repr += ": %s" % url
        if status:
            repr += ": %s" % status

        return "<%s>" % repr


    @property
    def hasStatus(self):
        return bool(self.version is not None
                and 0 < self.status < 1000
                and self.message is not None)


    def gotStatus(self, version, status, message):
        status = int(status)
        assert 0 < status < 1000, "Invalid status: %r" % status

        self.version = version
        self.status = status
        self.message = message


    @property
    def decoders(self):
        return self.contentDecoders


    def gotHeader(self, key, val):
        key = key.lower()  # just for normalcy; headers are insensitive

        self.headers.setdefault(key, [])
        self.headers[key].append(val)

        if key == "connection":
            if val == "close":
                self.closeConnection = True

        # transer-encodings handled by protocol

        elif key == "content-encoding":
            encodings = val.lower().split(",")
            self.contentDecoders += loadDecoders(encodings)


    def dataReceived(self, data):
        data = self.decodeData(data)

        self._dataLength += len(data)
        self.contentMD5.update(data)

        self.handleData(data)


    def decodeData(self, data):
        origLen = len(data)
        final = bool(origLen == 0)
        for decoder in self.decoders:
            data = decoder.decode(data, final)
        return data


    def handleData(self, data):
        """Called with data as it is decoded.
        
        Override this method
        """
        pass


    def done(self):
        self.dataReceived("")


    def info(self):
        """urllib2 API compatibility"""
        import mimetools
        headers = ("%s: %s\n" % kv for kv in self.headers.iteritems())
        return mimetools.Message(StringIO(str().join(headers)))


    def verifyDigest(self):
        md5Headers = self.headers.get("content-md5")
        if md5Headers is not None:
            assert len(md5Headers) == 1
            givenMD5 = md5Headers[0]

            calculatedMD5 = b64encode(self.contentMD5.digest())
            if givenMD5 != calculatedMD5:
                raise MD5Mismatch(self, calculatedMD5)


class LineResponse(Response):

    def __init__(self, request, url, method="GET"):
        Response(self, request, url, method)
        self._data = ""


    def handleData(self, data):
        """Buffer and yield lines."""
        if data == "":
            # Flush unterminated lines.
            if self._data:
                self.handleLine(self._data)

        else:
            self._data += data

            # partition() sets self._data to '' when a newline is not found.
            # When a newline is not found, line contains unterminated data.
            (line, sep, self._data) = self._data.partition("\n")
            while self._data:
                self.handleLine(line)
                (line, sep, self._data) = self._data.partition("\n")
            self._data = line


    def handleLine(self, line):
        pass




class StreamResponse(Response):
    """Response that is written to a stream"""

    def __init__(self, request, url, method="GET", headers=None, **kw):
        Response.__init__(self, request, url, method, headers, **kw)
        self.stream = kw.get("stream") or StringIO()

    def handleData(self, data):
        self.stream.write(data)


class BufferedResponse(StreamResponse):
    """Response that is written to a buffer"""

    @property
    def content(self):
        return self.stream.getvalue()


class FileResponse(StreamResponse):
    """Response that is written to file"""

    def __init__(self, request, url, path, method="GET", headers=None, **kw):
        kw["stream"] = open(path, "w")
        StreamResponse.__init__(self, request, url, method, headers, **kw)
        self.filePath = path

    def __repr__(self):
        return "<%s: %s: %s: %s>" % (self.__class__.__name__, self.method,
                self.url, self.filePath)

    def __del__(self):
        self.stream.close()

    def done(self):
        self.stream.close()


class Request(Message, urllib2_Request):
    # urllib2 compatibility is maintained for things like cookielib.

    # This dance is necessary because urllib2.Request.__init__ sets host and
    # port attributes to None.
    host = None
    port = None

    responseClass = BufferedResponse


    def __init__(self, url, method="GET", headers=None, data=None,
                 downloadTo=None, closeConnection=False, proxy=None,
                 redirectedFrom=None, unredirectedHeaders=None, **kw):
        """
        """
        headers = headers or dict()
        urllib2_Request.__init__(
                self, str(url), data=data, headers=headers,
                origin_req_host=kw.get("origin_req_host", redirectedFrom),
                unverifiable=kw.get("unverifiable", False),
            )
        Message.__init__(self, url, method, self.headers)
        self.host = self._url.host
        self.port = self._url.port
        self.setProxy(proxy)

        assert isinstance(self.headers, util.InsensitiveDict)
        unredirectedHeaders = unredirectedHeaders or dict()
        self.unredirectedHeaders = util.InsensitiveDict(unredirectedHeaders)

        self.closeConnection = closeConnection is True

        self.downloadTo = downloadTo
        self.redirectedTo = None
        self.redirectedFrom = tuple()
        self.response = defer.Deferred()


    @classmethod
    def fromRequest(klass, request, **kwArgs):
        from copy import deepcopy
        kw = dict(
                closeConnection = request.closeConnection,
                data = request.data,
                downloadTo = request.downloadTo,
                headers = deepcopy(request.headers),
                method = request.method,
                redirectedFrom = request.redirectedFrom,
                unredirectedHeaders = deepcopy(request.unredirectedHeaders),
                url = request.url,
            )
        kw.update(kwArgs)
        url = kw.pop("url")
        return klass(url, **kw)


    def copy(self, **kwArgs):
        return self.fromRequest(self, **kwArgs)


    def setData(self, data):
        if data:
            self.headers.setdefault("Content-length", len(data))

        elif "Content-length" in self.headers:
            del self.headers["Content-length"]

        self.data = data


    def redirect(self, location):
        self.redirectedTo = url = self.url.click(location)
        return self.copy(redirectedFrom=self, url=url)


    @property
    def redirected(self):
        return self.redirectedTo is not None


    def buildResponse(self):
        downloadTo = self.downloadTo
        if isinstance(downloadTo, basestring):
            response = FileResponse(self, self.url, downloadTo, self.method)

        elif hasattr(downloadTo, "write"):
            response = StreamResponse(self, self.url, self.method,
                    stream=downloadTo)

        else:
            klass = self.responseClass if self.responseClass else Response
            response = klass(self, self.url, self.method)

        return response


    def prepareHeaders(self):
        if self.data:
            self.headers["Content-Length"] = "%d" % len(self.data)

        self.headers.setdefault("Host", self.host)

        if self.closeConnection:
           self.headers.setdefault("Connection", "close")

        return self.headers



    # Compat

    @property
    def unredirected_headers(self):
        return self.unredirectedHeaders


    def has_data(self):
        return getattr(self, "data", None) is not None

    hasData = lambda s: s.has_data()


    def set_proxy(self, proxy):
        assert proxy is None or isinstance(proxy, Proxy), \
                "Expected Proxy, got %s" % proxy.__class__.__name__
        self.proxy = proxy

    setProxy = lambda s, p: s.set_proxy(p)


    def get_proxy(self):
        return self.proxy

    getProxy = lambda s, p: s.get_proxy(p)



