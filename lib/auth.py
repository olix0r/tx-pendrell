import hashlib

from twisted.internet.defer import maybeDeferred
from zope.interface import Interface, Attribute, implements
from pendrell import log


class IAuthenticator(Interface):

    schemes = Attribute("Sequence of authentication schemes")
    secure = Attribute("True iff this authorization is plaintext-safe")

    def authorize(scheme, **params):
        """Generate an authorization string."""



class UserPassAuthenticatorBase(object):
    implements(IAuthenticator)

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def authorize(self, **params):
        raise NotImplementedError()



class BasicAuthenticator(UserPassAuthenticatorBase):

    schemes = ("Basic", )
    secure = False

    def authorize(self, scheme, **params):
        """
        """
        cred =  "%s:%s" % (self.username, self.password)
        return "{scheme} {params}".format(scheme=scheme,
                params=cred.encode("base64").replace("\n", ""))



class DigestAuthenticator(UserPassAuthenticatorBase):

    schemes = ("Digest", )
    secure = True
    defaultAlgorithm = "md5"

    def authorize(self, scheme, **params):
        """Compute the digested authentication token as specfied by RFC 2617.

        Arguments:
            params --  Dictionary with the following keys:
                algorithm [default: "MD5"] --
                        Currently only the MD5 digest algorithm is supported.
                realm --  Authentication realm as specified by the server.
                method --  Request method (e.g. GET, POST)
                uri --  URI of the requested resource.
                nonce --  Server-provided nonce value.
        """
        log.debug("Beginning digest auth: {0!r}".format(params))

        algorithm = params.get("algorithm", self.defaultAlgorithm).lower()
        realm = params["realm"]
        method = params["method"]
        uri = params["uri"]
        nonce = params["nonce"]

        rsp = self._generateResponse(algorithm, realm, method, uri, nonce)

        return ("{scheme} username=\"{username}\", realm=\"{realm}\", "
                "nonce=\"{nonce}\", uri=\"{uri}\", response=\"{rsp}\""
                ).format(scheme=scheme, username=self.username, realm=realm,
                        nonce=nonce, uri=uri, rsp=rsp)


    @staticmethod
    def _generateResponse(algorithm, realm, method, uri, nonce):
        r1 = hashlib.new(algorithm, 
                "{0.username}:{1}:{0.password}".format(self, realm)
                ).hexdigest()

        r2 = hashlib.new(algorithm,
                "{0}:{1}".format(method, uri)
                ).hexdigest()

        rsp = hashlib.new(algorithm,
                "{0}:{1}:{2}".format(r1, nonce, r2)
                ).hexdigest()

        return rsp



__id__ = """$Id: agent.py 84 2010-06-01 16:01:45Z ver $"""[5:-2]

