import base64

from twisted.internet.defer import inlineCallbacks, returnValue, DeferredList
from pendrell.agent import Agent


class PendrellTestMixin(object):

    timeout = 60
    agentClass = Agent

    def setUp(self):
        self.agent = self.agentClass()

    def tearDown(self):
        return self.agent.cleanup()


    def getPages(self, count, url):
        ds = list()
        for i in xrange(0, count):
            d = self.getPage(url)
            ds.append(d)
        return DeferredList(ds)


    def getPage(self, url, **kw):
        return self.agent.open(url, **kw)


    @inlineCallbacks
    def getPageLength(self, url):
        response = yield self.getPage(url)
        returnValue(response.count)


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



try:
    trialIsOnline

except NameError:
    from urllib2 import urlopen
    try:
        urlopen("http://www.yahoo.com/")

    except:
        trialIsOnline = False

    else:
        trialIsOnline = True


