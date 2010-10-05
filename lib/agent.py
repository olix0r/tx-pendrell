"""
The goal of this prototype is to allow persistent HTTP connections through
twisted web by splitting the t.web.client.HTTPPageGetter into several classes:
an Agent, a Request, and a Requester.  Requests are submitted to the Agent.  The
Agent dispatches each request to a Requester, which communicates with each 

The convenience subroutines, getPage() and downloadPage() are provided to be
compatible, or at least similar to, twisted's interface.

TODO
  - Proxy Auto-Config (PAC) [http://code.google.com/p/pacparser/]
  - Provide a subclass of RobotParser that uses this interface.
"""

import cookielib, sys

from twisted import version as txVersion
from twisted.internet import (error as netErr,
        interfaces as netInterfaces, protocol, reactor)
from twisted.internet.defer import (
        Deferred, DeferredList,
        maybeDeferred, inlineCallbacks, returnValue)
from twisted.python import failure, util
from twisted.web import client as webClient, http
parseUrl = webClient._parse

from zope.interface import Attribute, Interface, implements

import pendrell
from pendrell import log
from pendrell.error import (RedirectedResponse, TooManyConnections,
        UnauthorizedResponse, InsecureAuthentication)
from pendrell.messages import Request
from pendrell.requester import Multiplexer, HTTPRequester, HTTPSRequester
from pendrell.proxy import Proxy, Proxyer


_PACKAGE = pendrell.version.package
_VERSION = pendrell.version.short()

_MAX_TOTAL_CONNECTIONS = 30  # ???
_MAX_CONNECTIONS_PER_SITE = 2


# getPage() & downloadPage() are for a semblance of API compatibility with
# twisted.web.client.

_AGENT = None

def getPage(url, agent=None, **kw):
    """Request a remote resource.

    Similar to twisted.web.getPage.

    Arguments:
        url --  A URL str OR an instance of URLPath OR an instance of Request
        agent --  An instance of Agent.  If not specified, a default agent
                  will be used (and cached for future calls with no specified
                  Agent).
    Keyword Arguments:
        Other keyword arguments are passed to agent.open()
    Returns:
        A Deferred:
            Callback --  an instance of Response
            Errback --   most likely an instance of WebError
    """
    global _AGENT
    if agent is None:
        agent = _AGENT = _AGENT or Agent()
    return agent.open(url, **kw)
 

def downloadPage(url, downloadTo, **kw):
    """Request and download it directyl to disk..

    Similar to twisted.web.dowloadPage.

    Arguments:
        url --  A URL str OR an instance of URLPath OR an instance of Request
        pathOrStream --
                A file path (str) or object (file) to which the response will be
                written.
    Returns:
        A Deferred:
            Callback --  an instance of Response
            Errback --   most likely an instance of WebError
    """
    kw["downloadTo"] = downloadTo
    return getPage(url, **kw)



class Agent(object):
    """User agent."""

    maxRedirects = 5

    identifier = "{pkg}/{ver} ({txPkg}/{txVer}; Python/{pyVer})".format(
            pkg=_PACKAGE.capitalize(), ver=_VERSION,
            txPkg=txVersion.package.capitalize(), txVer=txVersion.short(),
            pyVer="{0}.{1}.{2}".format(*sys.version_info))

    maxConnections = _MAX_TOTAL_CONNECTIONS
    maxConnectionsPerSite = _MAX_CONNECTIONS_PER_SITE
    
    preferredTransferEncodings = ("gzip", "deflate", )
    preferredConnection = "keep-alive"

    requestClass = Request
    followRedirect = True


    def __init__(self, **kw):
        """Constructor.
        
        Keyword Arguments:
            authenticators -- A list of IAuthenticators [default: []]
            cookieJar -- [default: cookielib.CookieJar()]
            followRedirect --  [default: True]
            identifier --  [default: self.identifier]
            maxConnections --  [default: self.maxConnections]
            maxConnectionsPerSite --  [default: self.maxConnectionsPerSite]
            preferredConnection --  [default: "keep-alive"]
            preferredTransferEncodings -- [default: ("gzip", "deflate")]
            requestClass --  [default: Request]
            resolver --  [default: reactor.resolver]
        """
        self.secure = kw.pop("secure", False)
        self.identifier = kw.pop("identifier", self.identifier)

        self.authenticators = kw.pop("authenticators", [])

        if "followRedirect" in kw:
            self.followRedirect = kw["followRedirect"]
        if "maxConnections" in kw:
            self.maxConnections = int(kw["maxConnections"])
        if "maxConnectionsPerSite" in kw:
            self.maxConnectionsPerSite = int(kw["maxConnectionsPerSite"])
        if "preferredConnection" in kw:
            self.preferredConnection = kw["preferredConnection"]
        if "preferredTransferEncodings" in kw:
            self.preferredTransferEncodings = kw["preferredTransferEncodings"]
        if "requestClass" in kw:
            self.requestClass = kw["requestClass"]

        self._timeout = kw.pop("timeout", None)
        self._cookieJar = kw.pop("cookieJar", cookielib.CookieJar())
        self._proxyer = kw.pop("proxyer", Proxyer())
        self._resolver = kw.pop("resolver", reactor.resolver)
        self._authorizationCache = dict()
        self._requesterCache = dict()
        self._requesterCacheOrder = []
        self._requestQueue = dict()


    def __str__(self):
        return self.identifier

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.identifier)

    def __del__(self):
        self.cleanup()

    @inlineCallbacks
    def open(self, request, authenticator=None, authenticators=None,
            followRedirect=None, proxy=None, _redirectCount=0, _unauthCount=0,
            **kw):
        """Setup and issue a request.

        Arguments:
            request -- A URL str OR an instance of URLPath OR Request.
        Keyword Arguments:
            authenticator [default: None] --
                    If specified and not None, an instance of Authenticator
            followRedirect [default: self.followRedirect] --
                    False if the response should callback with a redirect
                    response instead of following the redirect.
            proxy --
                    An instance of Proxy.
            
            Additional keyword arguments are passed to the constructor of
            self.requestClass.
        """
        request = self.buildRequest(request, **kw)

        assert proxy is None or isinstance(proxy, Proxy)
        timeout = kw.get("timeout", self._timeout)
        if followRedirect is None:
            followRedirect = self.followRedirect

        authorization = self._getCachedAuthorization(request)
        if authorization:
            request = self._buildAuthenticatedRequest(request, authorization)

        if proxy:
            request.setProxy(proxy)

        requester = self.getRequester(request, timeout=timeout)
        try:
            response = yield requester.issueRequest(request)

        except RedirectedResponse, rr:
            if not followRedirect \
                    or _redirectCount == self.maxRedirects \
                    or rr.status == http.SEE_OTHER:
                raise

            log.debug("Redirecting to %r" % (rr.location))
            response = yield self.open(
                    request.redirect(rr.location),
                    followRedirect = followRedirect,
                    proxy = proxy,
                    _redirectCount = _redirectCount+1,
                    authenticator = authenticator,
                    authenticators = authenticators,
                    _unauthCount = _unauthCount,
                    **kw)

        except UnauthorizedResponse, ur:
            if authorization:
                self._invalidateAuthorization(request)
            if _unauthCount == self.maxRedirects:
                raise

            authenticators = authenticators or self.authenticators[:]
            if authenticator:
                authenticators.insert(0, authenticator)

            authorization = yield self.getAuthorization(ur, authenticators)
            # N.b. all tried invalid/exhuasted authenticators have been popped
            # from authers

            request = self._buildAuthenticatedRequest(request, authorization)
            log.debug("Authenticating with: %r" % request)
            response = yield self.open(request,
                    followRedirect = followRedirect,
                    proxy = proxy,
                    _redirectCount = _redirectCount,
                    authenticators = authenticators,
                    _unauthCount = _unauthCount+1,
                    **kw)
            self._cacheAuthorization(request, authorization)

        else:
            response.verifyDigest()
            self.extractCookies(response)

        returnValue(response)


    @inlineCallbacks
    def getAuthorization(self, unauth, authenticators):
        authenticators = authenticators[:]
        authorization = None
        while authenticators and authorization is None:
            authenticator = authenticators.pop(0)
            for scheme, params in unauth.challenges:
                if self._supportedAuthenticationScheme(scheme, authenticator):
                    try:
                        authorization = yield maybeDeferred(
                                authenticator.authorize, scheme, **params)
                    except Exception, e:
                        log.debug(e)

        if not authorization:
            raise unauth

        self.activeAuthenticator = authenticator
        returnValue(authorization)



    def _cacheAuthorization(self, request, authorization):
        key = self._getRequesterKey(request)
        self._authorizationCache[key] = authorization

    def _getCachedAuthorization(self, request):
        key = self._getRequesterKey(request)
        return self._authorizationCache.get(key)

    def _invalidateAuthorization(self, request):
        key = self._getRequesterKey(request)
        return self._authorizationCache.pop(key)


    def _supportedAuthenticationScheme(self, scheme, authenticator):
        if authenticator:
            schemes = authenticator.schemes
            for s in schemes:
                if s.upper() == scheme.upper():
                    return True
        return False


    def _isSecureRequest(self, requester, authenticator):
        return bool(self.secure or requester.secure or authenticator.secure)


    _authHeader = "Authorization"

    def _buildAuthenticatedRequest(self, request, authorization):
        return request.copy(headers={self._authHeader:authorization})


    def extractCookies(self, response):
        assert response is not None
        self._cookieJar.extract_cookies(response, response.request)
        return response


    def getRequester(self, request, **kw):
        key = self._getRequesterKey(request)
        if key in self._requesterCache:
            # Reset order
            self._requesterCacheOrder.remove(key)
            self._requesterCacheOrder.insert(0, key)
            requester = self._requesterCache[key]

        elif request.proxy is not None:
            request.proxy.setRemote(request.host, request.port)
            requester = request.proxy
            # XXX reset timeout?

        else:
            if len(self._requesterCache) == self.maxConnections:
                killKey = self._requesterCacheOrder.pop()
                self._requesterCache.pop(killKey)

            if self._proxyer:
                proxy = self._proxyer.getRequester(request)
            else:
                proxy = None

            if proxy:
                request.setProxy(proxy)
                proxy.setRemote(request.host, request.port)
                requester = self._requesterCache[key] = proxy

            else:
                requester = self._buildRequester(request, **kw)
                self._requesterCache[key] = requester
            self._requesterCacheOrder.insert(0, key)

        return requester


    def _getRequesterKey(self, request):
        return "%s://%s" % (request.url.scheme, request.url.netloc)


    def buildRequest(self, request, **kw):
        if not isinstance(request, Request):
            request = self.requestClass(str(request), **kw)

        headers = kw.get("headers", dict())
        request.headers.update(headers)

        if self.preferredConnection:
            request.headers.setdefault("Connection", self.preferredConnection)

        if self.preferredTransferEncodings:
            request.headers.setdefault("TE",
                    ",".join(self.preferredTransferEncodings))

        request.headers.setdefault("User-agent", str(self.identifier))

        unredirected = kw.pop("unredirectedHeaders", dict())
        request.unredirectedHeaders.update(unredirected)

        self._cookieJar.add_cookie_header(request)

        return request

    
    #
    # TODO Load RequesterFactories as Plugins
    #
    _requesterClasses = {
        "http": HTTPRequester,
        "https": HTTPSRequester,
        }

    def _buildRequester(self, request, **kw):
        scheme = request.scheme

        kw.setdefault("maxConnections", self.maxConnectionsPerSite)

        host, port = request.host, request.port
        requesterClass = self._requesterClasses[scheme]
        requester = Multiplexer(requesterClass, scheme, host, port, **kw)

        return requester



    def cleanup(self):
        deferreds = list()
        for requester in self._requesterCache.itervalues():
            d = requester.loseConnection()
            deferreds.append(d)

        return DeferredList(deferreds)



__id__ = """$Id$"""[5:-2]

