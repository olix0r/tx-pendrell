import os

from twisted.internet import error as netErr, protocol, reactor
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.trial.unittest import TestCase
from twisted.web.resource import Resource as _Resource

from pendrell import log
from pendrell import error
from pendrell.cases.http_server import Site
from pendrell.cases.md5_server import MD5Root
from pendrell.cases.util import PendrellTestMixin, trialIsOnline



class AcceptEncodingTests(PendrellTestMixin, TestCase):
    """http://www.yahoo.com"""

    url = "http://www.yahoo.com"

    if not trialIsOnline:
        skip = "Offline mode"

    @inlineCallbacks
    def test_200AcceptEncodingDeflate(self):
        headers = {"Accept-Encoding": "deflate",}
        response = yield self.getPage(self.url, headers=headers)
        self.assertEquals(200, response.status)
        self.assertEquals(["deflate",], response.headers.get("Content-Encoding"))

    test_200AcceptEncodingDeflate.skip = "No readily available server support."


    @inlineCallbacks
    def test_200AcceptEncodingGzip(self):
        headers = {"Accept-Encoding": "gzip",}
        response = yield self.getPage(self.url, headers=headers)
        self.assertEquals(200, response.status)
        self.assertEquals(["gzip",], response.headers.get("Content-Encoding"))




class PendrellDownloadTest(PendrellTestMixin, TestCase):

    if not trialIsOnline:
        skip = "Offline mode"

    def setUp(self):
        PendrellTestMixin.setUp(self)
        from tempfile import mkstemp
        fd, self.tempPath = mkstemp()
        os.close(fd)

    @inlineCallbacks
    def tearDown(self):
        os.unlink(self.tempPath)
        yield PendrellTestMixin.tearDown(self)


    @inlineCallbacks
    def test_downloadRedirectedYahooToPath(self):
        url = "http://www.yahoo.com/"
        gzipHeaders = {"Accept-encoding": "gzip", }

        page = yield self.getPage(url,
                downloadTo = self.tempPath,
                headers = gzipHeaders)
        self.assertEquals(200, page.status)
        self.assertHeader(page, "Content-encoding", "gzip")

        contentLength = len(page)
        fileSize = os.stat(self.tempPath).st_size
        self.assertEquals(contentLength, fileSize)


    @inlineCallbacks
    def test_downloadYahooToPath(self):
        url = "http://m.www.yahoo.com/"
        page = yield self.getPage(
                url, downloadTo = self.tempPath,
                headers = {"Accept-encoding": "gzip", },
            )
        self.assertEquals(200, page.status)
        self.assertHeader(page, "Content-encoding", "gzip")

        contentLength = len(page)
        fileSize = os.stat(self.tempPath).st_size
        self.assertEquals(contentLength, fileSize)



class MD5Test(PendrellTestMixin, TestCase):

    _lo0 = "127.0.0.1"
    http_port = 8085


    def setUp(self):
        PendrellTestMixin.setUp(self)

        log.debug("Setting up md5 site.")
        self.md5Server = reactor.listenTCP(
                self.http_port,
                Site(MD5Root()),
                interface=self._lo0)
        log.debug("MD5 site is listening.")


    @inlineCallbacks
    def tearDown(self):
        log.debug("Tearing down md5 site.")
        yield PendrellTestMixin.tearDown(self)
        yield self.md5Server.stopListening()


    @property
    def _baseURL(self):
        return "http://%s:%d" % (self._lo0, self.http_port)


    @inlineCallbacks
    def test_validMD5(self):
        url = "%s/valid" % self._baseURL

        try:
            response = yield self.getPage(url)
        except error.MD5Mismatch:
            valid = False
        else:
            valid = True
        self.assertTrue(valid)



    @inlineCallbacks
    def test_invalidMD5(self):
        url = "%s/invalid" % self._baseURL
        try:
            response = yield self.getPage(url)

        except error.MD5Mismatch:
            invalid = True
        else:
            invalid = False

        self.assertTrue(invalid, "Expected invalid MD5 digest in header")


class RequestTest(PendrellTestMixin, TestCase):

    _lo0 = "127.0.0.1"
    http_port = 8056
    timeout = 5

    @property
    def _baseURL(self):
        return "http://%s:%d" % (self._lo0, self.http_port)


    class Resource(_Resource):
        def __init__(self):
            _Resource.__init__(self)
            self.putChild("", self)

        isLeaf = True
        def render_GET(self, request):
            return "Me encanta los tacos!\n"


    def setUp(self):
        PendrellTestMixin.setUp(self)
        self.site = Site(self.Resource())
        self.server = reactor.listenTCP(self.http_port, self.site,
                interface=self._lo0)


    @inlineCallbacks
    def tearDown(self):
        yield PendrellTestMixin.tearDown(self)
        yield self.server.stopListening()


    @inlineCallbacks
    def test_request_root(self):
        response = yield self.getPage(self._baseURL+"/")
        self.assertEquals([("GET", "/", "HTTP/1.1"),], self.site.journal)
        

    @inlineCallbacks
    def test_request_query(self):
        response = yield self.getPage(self._baseURL+"/?whatup=notmuch#morefun")
        self.assertEquals([("GET", "/?whatup=notmuch#morefun", "HTTP/1.1"),],
                self.site.journal)
 
    test_request_query.todo = "bug reported by kkszysiu (@github)"


