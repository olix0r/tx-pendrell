import re

from twisted.internet import error as netErr
from twisted.python import failure
from twisted.web import client as webClient, error as webErr, http

#
# Work around a bug in twisted.web.errors in python2.6
#   http://twistedmatrix.com/trac/ticket/4456
#
from warnings import filterwarnings
filterwarnings("ignore", category=DeprecationWarning,
        message="BaseException\.message has been deprecated as of Python 2\.6")


class FailableMixin:

    @classmethod
    def Failure(klass, *args):
        return failure.Failure(klass(*args))



class WebError(webErr.Error, FailableMixin):

    def __init__(self, response):
        webErr.Error.__init__(self, response.status,
                message=response.message,
                response=response)


class IncompleteResponse(WebError, webClient.PartialDownloadError):
    pass


class RedirectedResponse(webErr.PageRedirect, WebError):
    def __init__(self, response):
        webErr.PageRedirect.__init__(self, response.status,
                location=response.headers["location"][0],
                response=response)


class UnauthorizedResponse(WebError):

    headerRegex = re.compile("([a-z]+)=\"([^\"]+)\"(?:, |$)", re.IGNORECASE)

    def __init__(self, response):
        assert response.status == http.UNAUTHORIZED
        WebError.__init__(self, response)

        authenticationValues = response.headers["www-authenticate"]
        assert len(authenticationValues) == 1

        authentication = authenticationValues[0]
        scheme, params = authentication.split(None, 1)

        self.authScheme = scheme = scheme.upper()

        paramList = self.headerRegex.findall(params)
        assert paramList

        self.authParams = params = dict(paramList)
        assert "realm" in params

        self.authParams["method"] = response.method
        self.authParams["uri"] = response.request.path



class MD5Mismatch(WebError):

    def __init__(self, response, calculatedDigest):
        self.calculatedDigest = calculatedDigest
        md5Values = response.headers["content-md5"]
        self.expectedDigest = md5Values.pop(0)
        WebError.__init__(self, response)

    def __str__(self):
        return "calculated=%s expected=%s" % (
                self.calculatedDigest, self.expectedDigest)

    def __repr__(self):
        return "<%s: calculated=%s expected=%s>" % (
                self.__class__.__name__, self.calculatedDigest,
                self.expectedDigest)


class ResponseTimeout(WebError, netErr.TimeoutError):

    def __init__(self, response, timeout):
        WebError.__init__(self, response)
        self.timeout = timeout

    def __str__(self):
        return "%Timed out after %s" % (self.timeout)

    def __repr__(self):
        return "<%s: timeout=%s>" % (self.__class__.__name__, self.timeout)



class RetryResponse(WebError):

    def __init__(self, response):
        retryValues = response.headers["Retry-After"]
        self.retryAfter = int(retryValues.pop(0))

        WebError.__init__(self, response)


    def __str__(self):
        return "%s: Retry after %s" % (self.response.status, self.retryAfter)

    def __repr__(self):
        return "<%s: retryAfter=%s>" % (
                self.__class__.__name__,
                self.retryAfter)



class InsecureAuthentication(Exception):
    def __init__(self, response, authenticator):
        Exception.__init__(self, response, authenticator)
        self.authenticator = response
        self.response = response


class TooManyConnections(Exception, FailableMixin):

    def __init__(self, url):
        self.url = url


__id__ = """$Id: agent.py 84 2010-06-01 16:01:45Z ver $"""[5:-2]

