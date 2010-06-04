
from twisted.internet import reactor
from twisted.internet.defer import (
        Deferred, gatherResults,
        inlineCallbacks, returnValue,
        setDebugging as setDeferredDebugging)
from twisted.trial.unittest import TestCase

from pendrell import auth, error, log, messages
from pendrell.agent import Agent

from pendrell.cases.util import PendrellTestMixin, trialIsOnline


setDeferredDebugging(True)



class JigsawTestMixin(PendrellTestMixin):
    """http://jigsaw.w3.org/HTTP/"""

    @inlineCallbacks
    def test_200pipelinedChunked(self):
        url = "http://jigsaw.w3.org/HTTP/ChunkedScript"
        knownDigest = "de032b1da0a64c051538eb568f68afba"

        responses = yield self.getPages(2, url)

        for _, response in responses:
            self.assertEquals(200, response.status)
            self.assertMD5Digest(knownDigest, response)


    @inlineCallbacks
    def test_200pipelinedUnchunked(self):
        url = "http://jigsaw.w3.org/HTTP/"

        responses = yield self.getPages(2, url)

        for _, response in responses:
            self.assertEquals(200, response.status)


    @inlineCallbacks
    def test_200chunking(self):
        """http://jigsaw.w3.org/HTTP/ChunkedScript"""
        url = "http://jigsaw.w3.org/HTTP/ChunkedScript"
        knownDigest = "de032b1da0a64c051538eb568f68afba"

        response = yield self.getPage(url)

        self.assertEquals(200, response.status)
        self.assertMD5Digest(knownDigest, response)


    @inlineCallbacks
    def test_200TEGzip(self):
        response = yield self.getPage(
                "http://jigsaw.w3.org/HTTP/TE/foo.txt",
                headers = {"TE": "gzip", },
            )

        self.assertEquals(200, response.status)
        self.assertHeader(response, "Transfer-Encoding", "gzip,chunked")
        self.assertEquals(18432, len(response))


    @inlineCallbacks
    def test_200TEDeflate(self):
        response = yield self.getPage(
                "http://jigsaw.w3.org/HTTP/TE/foo.txt",
                headers={"TE": "deflate"})

        self.assertEquals(200, response.status)
        self.assertHeader(response, "Transfer-Encoding", "deflate,chunked")
        self.assertEquals(18432, len(response))



    def test_200md5Match(self):
        url = "http://jigsaw.w3.org/HTTP/h-content-md5.html"
        d = self.getPage(url)
        d.addCallback(self.cb_assertStatus, 200)
        d.addCallback(self.cb_verifyContentLength)
        d.addCallback(self.cb_md5Digest64)
        d.addCallback(self.cb_assertMD5Match)
        return d


    redirectTo = "http://jigsaw.w3.org/HTTP/300/Overview.html"

    def test_301movedPermanently(self):
        """http://jigsaw.w3.org/HTTP/300/301.html"""
        d = self.getPage("http://jigsaw.w3.org/HTTP/300/301.html")
        d.addCallback(self.cb_assertRedirects, self.redirectTo)
        return d


    @inlineCallbacks
    def test_301noredirect(self):
        """http://jigsaw.w3.org/HTTP/300/301.html"""
        url = "http://jigsaw.w3.org/HTTP/300/301.html"
        try:
            response = yield self.getPage(url, followRedirect=False)

        except error.RedirectedResponse, rr:
            self.assertEquals(301, rr.status)
            self.assertEquals(self.redirectTo, rr.location)

        else:
            self.assertTrue(False)


    @inlineCallbacks
    def test_302found(self):
        """302 Redirect"""
        url = "http://jigsaw.w3.org/HTTP/300/302.html"
        response = yield self.getPage(url)
        self.assertEquals(self.redirectTo, response.url)


    @inlineCallbacks
    def test_303seeOther(self):
        """303 redirect"""
        requestURL = "http://jigsaw.w3.org/HTTP/300/Go_303"
        responseURL = "http://jigsaw.w3.org/HTTP/300/303_ok.html"

        try:
            response = yield self.getPage(requestURL, method="POST", data="foo=bar")

        except error.RedirectedResponse, rr:
            self.assertEquals(303, rr.status)
            self.assertEquals(responseURL, rr.location)

        else:
            self.assertTrue(False)


    @inlineCallbacks
    def test_307temporaryRedirect(self):
        """307 Redirect"""
        url = "http://jigsaw.w3.org/HTTP/300/307.html"
        response = yield self.getPage(url)
        self.assertEquals(self.redirectTo, response.url)


    #@inlineCallbacks
    #def test_414tooLong(self):
    #    """414  Redirect"""
    #    url = "http://jigsaw.w3.org/HTTP/400/toolong/"
    #    try:
    #        response = yield self.getPage(url)
    #    except error.RedirectedResponse, rr:
    #        self.assertEquals(414, rr.status)
    #    else:
    #        self.assertTrue(False)
    #
    #test_414tooLong.skip = "This isn't much of a client feature and " \
    #                       "testing it regularly is silly"


    @inlineCallbacks
    def test_503retryAfter(self):
        """http://jigsaw.w3.org/HTTP/h-retry-after.html"""
        url = "http://jigsaw.w3.org/HTTP/h-retry-after.html"
        try:
            response = yield self.getPage(url)

        except error.RetryResponse, rr:
            self.assertEquals(503, rr.status)
            self.assertTrue(0 < rr.retryAfter)

            if rr.retryAfter < self.timeout:
                def _sleepFor(time):
                    d = Deferred()
                    reactor.callLater(time, d.callback, True)
                    return d
                yield _sleepFor(rr.retryAfter)
                response = yield self.getPage(url)
                self.assertEquals(200, response.status)

        else:
            self.assertTrue(False)



    @inlineCallbacks
    def test_401basicAuth(self):
        self.agent.secure = False
        url = "http://jigsaw.w3.org/HTTP/Basic/"

        authenticator = auth.BasicAuthenticator("guest", "guest")
        response = yield self.getPage(url, authenticator=authenticator)

        self.assertEquals(200, response.status)


    @inlineCallbacks
    def test_401digestAuth(self):
        url = "http://jigsaw.w3.org/HTTP/Digest/"
        authenticator = auth.DigestAuthenticator("guest", "guest")
        response = yield self.getPage(url, authenticator=authenticator)
        self.assertEquals(200, response.status)


    @inlineCallbacks
    def test_401digestAuthMD5Sess(self):
        authenticator = auth.Authenticator("guest", "guest")
        response = yield self.getPage("http://jigsaw.w3.org/HTTP/Digest/")
        response.assertEquals(200, response.status)

    test_401digestAuthMD5Sess.todo = \
            "MD5-sess authentication is not yet implemented or testable."



class PendrellJigsawTest(JigsawTestMixin, TestCase):
    timeout = 10

    if not trialIsOnline:
        skip = "Offline mode"


