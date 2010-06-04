import hashlib

from twisted.internet.defer import maybeDeferred
from pendrell import log



class Authenticator(object):

    def __init__(self, username, password):
        self.username = username
        self.password = password


    def authorize(self, scheme, params):
        scheme = scheme.lower()
        try:
            authMaker = getattr(self, "authorize_%s" % scheme)
        except AttributeError:
            raise ValueError("Unsupported authorization scheme for %s: %s" % (
                             self.__class__.__name__,
                             scheme
                 ))
        else:
            return maybeDeferred(authMaker, params)



class BasicAuthenticator(Authenticator):

    def authorize_basic(self, params):
        """
        """
        cred =  "%s:%s" % (self.username, self.password)

        return "Basic %s" % cred.encode("base64").replace("\n", "")



class DigestAuthenticator(Authenticator):

    def authorize_digest(self, params):
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

        algorithm = params.get("algorithm", "md5").lower()
        realm = params["realm"]
        reqMethod = params["method"]
        reqURI = params["uri"]
        nonce = params["nonce"]

        # Compute digest response
        a1 = "%s:%s:%s" % (self.username, realm, self.password)
        a2 = "%s:%s" % (reqMethod, reqURI)
        a1Dig = hashlib.new(algorithm, a1).hexdigest()
        a2Dig = hashlib.new(algorithm, a2).hexdigest()
        rsp = "%s:%s:%s" % (a1Dig, nonce, a2Dig)
        rspDig = hashlib.new(algorithm, rsp).hexdigest()

        auth = "Digest " + ", ".join((
                "username=\"%s\"" % self.username,
                "realm=\"%s\"" % realm,
                "nonce=\"%s\"" % nonce,
                "uri=\"%s\"" % reqURI,
                "response=\"%s\"" % rspDig,
            ))
        return auth


__id__ = """$Id: agent.py 84 2010-06-01 16:01:45Z ver $"""[5:-2]

