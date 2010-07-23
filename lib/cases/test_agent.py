# TODO
# - test cookies

import os, random
from hashlib import md5

from twisted.cred import portal
from twisted.cred.error import LoginFailed, UnauthorizedLogin
from twisted.cred.checkers import ICredentialsChecker
from twisted.internet import error as netErr, protocol, reactor
from twisted.internet.defer import (
        Deferred, gatherResults,
        inlineCallbacks, returnValue,
        setDebugging as setDeferredDebugging)
from twisted.python import failure
from twisted.trial import unittest
from twisted.web.http import HTTPFactory
from twisted.web.guard import HTTPAuthSessionWrapper
from twisted.web.iweb import ICredentialFactory
from twisted.web.resource import IResource, Resource

from zope.interface import Interface, Attribute, implements

from pendrell import agent as pendrell, auth, error, log, messages
from pendrell.cases.http_server import Site
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
        self.server = reactor.listenTCP(self._port,
                _TimeoutServerFactory(),
                interface="127.0.0.1")

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



class IStoopidCredential(Interface):
    name = Attribute("What's yer name?")
    secret = Attribute("What's the secret, stoopid?")

class StoopidCredential(object):
    implements(IStoopidCredential)

    def __init__(self, name, secret):
        self.name, self.secret = name, secret

    def __repr__(self):
        return "{0.name}:'{0.secret}'".format(self)


class StoopidChecker(object):
    implements(ICredentialsChecker)

    credentialInterfaces = (IStoopidCredential, )

    secret = "I LIKE TAC0S!"

    def requestAvatarId(self, cred):
        log.msg("Requesting avatar id: {0}".format(cred))
        if cred.secret != self.secret:
            raise UnauthorizedLogin("Unauthorized login.")
        return cred.name


class StoopidCredentialFactory(object):
    implements(ICredentialFactory)

    credentialInterfaces = (IStoopidCredential, )

    scheme = "Stoopid"
    realm = "bocas@tacos"

    def getChallenge(self, request):
        return {"realm": self.realm, "question": "What's the password?", }

    def decode(self, response, request):
        log.msg("Building credentials")
        auth = self._parseAuth(response)
        try:
            creds = StoopidCredential(auth["name"], auth["secret"])
        except KeyError, ke:
            raise LoginFailed("{0!r} not in authorization.".format(*ke.args))
        log.msg("Built credentials: {0}".format(creds))
        return creds


    def _parseAuth(self, response):
        def unQuote(s):
            if s and (s[0] in "\"\'") and (s[0] == s[-1]):
                s = s[1:-1]
                return s

        auth = dict()
        log.msg("Parsing response: {0!r}".format(response))
        for segment in response.replace("\n", " ").split(","):
            log.msg("Parsing segment: {0!r}".format(segment))
            key, val = [s.strip() for s in segment.split("=", 1)]
            auth[key] = unQuote(val)

        return auth



class AuthorizationTest(unittest.TestCase):

    class Realm(object):
        implements(portal.IRealm)

        def requestAvatar(self, avId, mind, *ifaces):
            assert IResource in ifaces
            return (IResource, self.Resource(avId), lambda: avId)

        class Resource(Resource):
            implements(IResource)

            def __init__(self, avatar):
                Resource.__init__(self)
                self.avatar = avatar
                self.putChild("", self)

            def render_GET(self, request):
                return "ACCESS GRANTED %s\n" % self.avatar.upper()


    class JournalingAuthenticator(auth.UserPassAuthenticatorBase):

        schemes = ("Stoopid", )
        secure = False

        def __init__(self):
            self.journal = []

        def authorize(self, scheme, **params):
            self.journal.append((scheme, params))


    class StoopidAuthenticator(auth.UserPassAuthenticatorBase):

        schemes = ("Stoopid", )
        secure = False

        def __init__(self, name, secret):
            self.name = name
            self.secret = secret

        def authorize(self, scheme, **params):
            return ("{scheme} realm=\"{params[realm]}\","
                    "name=\"{name}\",secret=\"{secret}\"").format(
                    scheme=scheme,
                    params=params,
                    name=self.name,
                    secret=self.secret)


    class Guard(HTTPAuthSessionWrapper):

        def _login(self, creds):
            log.msg("Logging in: {0!r}".format(creds))
            return HTTPAuthSessionWrapper._login(self, creds)

        def _selectParseHeader(self, header):
            """Find an authentication scheme in a case-insensitive way."""
            log.debug("Finding an authenticator for {0}".format(header))
            scheme, elements = header.split(' ', 1)
            for fact in self._credentialFactories:
                if fact.scheme.lower() == scheme.lower():
                    log.debug("Found an authenticator: {0}".format(fact))
                    return (fact, elements)
            log.debug("No matching authenticator found for {0}".format(scheme))
            return (None, None)


    _port = 8015
    url = "http://localhost:%d/" % _port

    def setUp(self):
        self.agent = pendrell.Agent()
        rlm = self.Realm()
        ptl = portal.Portal(rlm, [StoopidChecker(),])
        guard = self.Guard(ptl, [StoopidCredentialFactory(),])
        self.site = Site(guard)
        self.server = reactor.listenTCP(self._port, self.site,
                interface="127.0.0.1")


    @inlineCallbacks
    def tearDown(self):
        yield self.agent.cleanup()
        yield self.server.stopListening()


    @inlineCallbacks
    def test_authorize_single(self):
        try:
            a = self.StoopidAuthenticator("Santo", StoopidChecker.secret)
            rsp = yield self.agent.open(self.url, authenticator=a)

        except Exception, err:
            self.fail(err)

        else:
            self.assertEquals("ACCESS GRANTED SANTO\n", rsp.content)


    @inlineCallbacks
    def test_authorize_installed(self):
        try:
            a = self.StoopidAuthenticator("Isla", StoopidChecker.secret)
            self.agent.authenticators.append(a)
            rsp = yield self.agent.open(self.url)

        except Exception, err:
            self.fail(err)

        else:
            self.assertEquals("ACCESS GRANTED ISLA\n", rsp.content)


    @inlineCallbacks
    def test_authorize_installed_journaled(self):
        try:
            a = self.StoopidAuthenticator("Isla", StoopidChecker.secret)
            j = self.JournalingAuthenticator()
            self.agent.authenticators = [j, a]
            rsp = yield self.agent.open(self.url)

        except Exception, err:
            self.fail(err)

        else:
            self.assertEquals("ACCESS GRANTED ISLA\n", rsp.content)
            self.assertEquals([
                ("Stoopid", {"realm": "bocas@tacos", "uri": "/",
                    "question": "What's the password?", "method": "GET",}),
                ], j.journal)


    @inlineCallbacks
    def test_authorize_installed_not_journaled(self):
        try:
            a = self.StoopidAuthenticator("Isla", StoopidChecker.secret)
            j = self.JournalingAuthenticator()
            self.agent.authenticators = [a, j]
            rsp = yield self.agent.open(self.url)

        except Exception, err:
            self.fail(err)

        else:
            self.assertEquals("ACCESS GRANTED ISLA\n", rsp.content)
            self.assertEquals([], j.journal)


