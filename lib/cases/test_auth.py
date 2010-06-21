from twisted.trial import unittest
from zope.interface.verify import verifyObject
from pendrell import auth


class BasicAuthTest(unittest.TestCase):

    def setUp(self):
        self.auth = auth.BasicAuthenticator("user", "p4ss")

    def test_constructor(self):
        self.assertTrue(verifyObject(auth.IAuthenticator, self.auth))
        self.assertEquals("user", self.auth.username)
        self.assertEquals("p4ss", self.auth.password)
        self.assertEquals(("Basic",), self.auth.schemes)


    def test_authorize(self):
        params = {"realm": "test", }
        authorization = self.auth.authorize("Basic", **params)
        self.assertEquals(
                "Basic " + "user:p4ss".encode("base64").strip(),
                authorization)


class DigestAuthTest(unittest.TestCase):
        
    creds = ("user", "p4ss")
    params = {
        "realm": "test",
        "algorithm": "sha256",
        "method": "GET",
        "uri": "http://localhost/",
        "nonce": "10"
        }


    class Authenticator(auth.DigestAuthenticator):
        staticResponse = "%RESPONSE%"
        @classmethod
        def _generateResponse(klass, *args):
            return klass.staticResponse


    def setUp(self):
        self.auth = self.Authenticator(*self.creds)

    def test_constructor(self):
        self.assertTrue(verifyObject(auth.IAuthenticator, self.auth))
        self.assertEquals("user", self.auth.username)
        self.assertEquals("p4ss", self.auth.password)
        self.assertEquals(("Digest",), self.auth.schemes)


    def test_authorize(self):
        authorization = self.auth.authorize("Digest", **self.params)
        scheme, authorization = authorization.split(" ", 1)
        self.assertEquals("DIGEST", scheme.upper())
        self.assertEquals({
                    "realm": self.params["realm"],
                    "nonce": self.params["nonce"],
                    "response": self.auth.staticResponse,
                    "uri": self.params["uri"],
                    "username": self.creds[0],
                },
                dict((k, v.strip("\"'")) for k, v in [
                        a.strip().split("=") for a in authorization.split(",")])
                )


