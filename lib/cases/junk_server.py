import os, math

from twisted.internet import reactor
from twisted.internet.defer import (
        Deferred, gatherResults,
        succeed,
        inlineCallbacks, returnValue)

from twisted.web import http
from twisted.web.resource import Resource

from pendrell import log
from pendrell.util import humanizeBytes, normalizeBytes, b64random
from pendrell.cases.http_server import Site, NOT_DONE_YET


CHUNK_SIZE= 64 * 1024

class JunkSiteTestMixin(object):

    _lo0 = "127.0.0.1"
    http_port = 8084
    chunkSize = CHUNK_SIZE

    def setUp(self):
        log.debug("Setting up junk site.")
        site = JunkSite(self.chunkSize)
        self.junkServer = reactor.listenTCP(self.http_port, site,
                interface=self._lo0)
        log.debug("Junk site is listening.")


    def tearDown(self):
        log.debug("Tearing down junk site.")
        return self.junkServer.stopListening()


    @property
    def _baseURL(self):
        return "http://%s:%d" % (self._lo0, self.http_port)


    @inlineCallbacks
    def _test_getJunk(self, size, suffix):
        url = "%s/%d.%s" % (self._baseURL, size, suffix)
        log.debug("Getting junk: %s" % url)
        count = yield self.getPageLength(url)
        bytes = normalizeBytes(size, suffix)
        self.assertEquals(bytes, count)


    def _test_getJunks(self, count, size, suffix):
        log.debug("Waiting for %d responses." % count)
        return gatherResults([
            self._test_getJunk(size, suffix) for i in xrange(0, count)
            ])




class JunkSite(Site):

    def __init__(self, chunkSize=CHUNK_SIZE):
        Site.__init__(self, JunkRoot(chunkSize))



class JunkRoot(Resource):

    isLeaf = False

    def __init__(self, chunkSize=CHUNK_SIZE):
        Resource.__init__(self)
        self._chunkSize = chunkSize

    def getChild(self, name, request):
        # Python2.6/3.0
        #log.debug("{0} getting child {1} for {2}".format(
        #          self, name, request))
        log.debug("%r getting child %s for %r" % (self, name, request))

        try:
            sizeDesc, suffix = name.split(".")
            relativeSize = long(sizeDesc)
            size = normalizeBytes(relativeSize, suffix)

        except (TypeError, ValueError), e:
            log.debug("Failed to determine size for %r: %r" % (name, e.args))
            child = Resource.getChild(self, name, request)

        else:
            child = Junk(size, self._chunkSize)

        return child



class Junk(Resource):
    
    isLeaf = True

    def __init__(self, size, chunkSize=CHUNK_SIZE):
        Resource.__init__(self)
        self.size = long(size)
        self.chunkSize = long(chunkSize or self.chunkSize)


    def render_GET(self, request):
        log.debug("%r rendering %d bytes for %r" % (self, self.size, request))
        d = self._writeJunk(request)
        return NOT_DONE_YET


    @inlineCallbacks
    def _writeJunk(self, request):
        chunkCount = long()
        writtenSize = long()
        while writtenSize != self.size:
            if writtenSize + self.chunkSize > self.size:
                writeSize = self.size - writtenSize
            else:
                writeSize = self.chunkSize

            writtenSize += writeSize
            log.debug("Writing chunk %d (%dB/%dB) of %r" % (
                    chunkCount, writeSize, writtenSize, request)) 
            chunkCount += 1
            yield self._writeJunkChunk(request, writeSize)
        assert writtenSize == self.size

        bytes, suffix = humanizeBytes(writtenSize)
        log.debug("Wrote %f%s in %d chunks for %r" % (
                bytes, suffix, chunkCount, request))
        request.finish()


    def _writeJunkChunk(self, request, chunkSize):
        chunk = b64random(chunkSize)
        assert len(chunk) == chunkSize

        def _write(data, d):
            request.write(data)
            d.callback(True)

        d = Deferred()
        reactor.callLater(0, _write, chunk, d)

        return d



