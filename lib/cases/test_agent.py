# TODO
# - test cookies

import os, random
from hashlib import md5

from twisted.internet import error as netErr, protocol, reactor
from twisted.internet.defer import (
        Deferred, gatherResults,
        inlineCallbacks, returnValue,
        setDebugging as setDeferredDebugging)
from twisted.python import failure
from twisted.trial import unittest

from pendrell import log
from pendrell import agent as pendrell, auth, error, messages
from pendrell.cases.server import JunkSite
from pendrell.cases.md5_server import MD5Site
from pendrell.cases.util import PendrellTestMixin, trialIsOnline

setDeferredDebugging(True)



class AgentTest(PendrellTestMixin, unittest.TestCase):

    timeout = 60

    def assertMD5Digest(self, expected, response):
        hexDigest = response.contentMD5.hexdigest()
        self.assertEquals(expected, hexDigest)

    def cb_md5Digest64(self, response):
        rawDigest = response.contentMD5.digest()
        b64Digest = base64.b64encode(rawDigest)
        return response, b64Digest

    def cb_assertStatus(self, response, status):
        self.assertEqual(response.status, status)
        return response

    def eb_assertStatus(self, reason, status):
        self.assertTrue(reason.check(error.WebError))
        self.assertEqual(reason.value.status, status)
        return reason

    def cb_assertRedirects(self, response, dstUrl):
        self.assertEqual(str(response.url), str(dstUrl))
        return response

    def assertHeader(self, response, key, expectedValue):
        values = response.headers.get(key)
        self.assertNotEqual(values, None)
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0], expectedValue)
        return response
    cb_assertHeader = assertHeader

    def cb_assertMD5Match(self, (response, digest)):
        self.cb_assertHeader(response, "content-md5", digest)
        return response

    def cb_verifyContentLength(self, response):
        if "content-length" in response.headers:
            self.assertHeader(response, "content-length", "%d" % len(response))
        return response




class DownloadTest(AgentTest):

    # XXX Why do these need to be remote tests?
    if not trialIsOnline:
        skip = "Offline mode"

    def setUp(self):
        from tempfile import mkstemp
        AgentTest.setUp(self)
        fd, self.tempPath = mkstemp()
        os.close(fd)


    def tearDown(self):
        AgentTest.tearDown(self)
        os.unlink(self.tempPath)


    def test_downloadToPath(self):
        d = self.agent.open(
                "http://www.yahoo.com/",
                downloadTo = self.tempPath,
                headers = {"Accept-encoding": "gzip", },
            )
        d.addCallback(self.cb_assertStatus, 200)
        d.addCallback(self.cb_assertHeader, "Content-encoding", "gzip")

        def cb_assertFileNotEmpty(response, path):
            fileSize = os.stat(path).st_size
            log.msg("%s is %dB: %r" % (path, fileSize,
                open(path).read()))
            self.assertTrue(fileSize > 500,
                    "Expected more than %d bytes" % fileSize)
            return response
        d.addCallback(cb_assertFileNotEmpty, self.tempPath)

        return d


class _TimeoutProtocol(protocol.Protocol):
    def dataReceived(self, data):
        self.transport.write("200")

class _TimeoutServerFactory(protocol.ServerFactory):
    protocol = _TimeoutProtocol


class TimeoutTest(PendrellTestMixin, unittest.TestCase):
    """Test request timeout functionality."""

    timeout = 5  # Test timeout
    requestTimeout = 2  # Request timeout (being tested)
    _port = 9798

    def setUp(self):
        PendrellTestMixin.setUp(self)
        self.server = reactor.listenTCP(self._port, _TimeoutServerFactory())

    def tearDown(self):
        PendrellTestMixin.tearDown(self)
        self.server.stopListening()


    @inlineCallbacks
    def test_timeout(self):
        from time import sleep
        try:
            rsp = yield self.getPage("http://127.0.0.1:%d/" % self._port,
                    timeout=self.requestTimeout)

        except netErr.TimeoutError:
            timedOut = True

        else:
            timedOut = False

        self.assertTrue(timedOut)


