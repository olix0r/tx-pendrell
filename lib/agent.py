"""
The goal of this prototype is to allow persistent HTTP connections through
twisted web by splitting the t.web.client.HTTPPageGetter into several classes:
an Agent, a Request, and a Requester.  Requests are submitted to the Agent.  The
Agent dispatches each request to a Requester, which communicates with each 

The convenience subroutines, getPage() and downloadPage() are provided to be
compatible, or at least similar to, twisted's interface.

TODO
  - Add Proxy support to Agent.open()
    - Make Requester an interface rather than a type.
    - HTTP
    - SOCKS 4a
    - SOCKS 5
    - Proxy Auto-Config (PAC) [http://code.google.com/p/pacparser/]
  - Finalize API and complete documentation
  - Constrain redirect loops.
  - Implement timeouts.
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
        self._requesterCache = dict()
        self._requestQueue = dict()


    def __str__(self):
        return self.identifier

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.identifier)

    def __del__(self):
        self.cleanup()

    @inlineCallbacks
    def open(self, request, authenticator=None, followRedirect=None,
            proxy=None, _redirectCount=0, **kw):
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
        log.debug("Opening {0}".format(request))
        log.debug("Authenticator: {0}".format(authenticator))

        assert proxy is None or isinstance(proxy, Proxy)
        timeout = kw.get("timeout", self._timeout)
        if followRedirect is None:
            followRedirect = self.followRedirect

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

            log.msg("Redirecting to %r" % (rr.location))
            response = yield self.open(
                    request.redirect(rr.location),
                    authenticator = authenticator,
                    followRedirect = followRedirect,
                    proxy = proxy,
                    _redirectCount = _redirectCount+1,
                    **kw)
            log.msg("Redirected to %r" % response)

        except UnauthorizedResponse, ur:
            if self._supportedAuthenticationScheme(ur.scheme, authenticator):
                if not self._isSecureRequest(requester, authenticator):
                    raise InsecureAuthentication(ur.response, authenticator)

                try:
                    auth = yield maybeDeferred(
                            authenticator.authorize, ur.scheme, **ur.params
                            )
                except:
                    log.err()
                    raise ur
                if not auth:
                    raise ur
                log.msg("Built authentication for %r: %r" % (request, auth))

                authenticated = self._buildAuthenticatedRequest(request, auth)
                log.msg("Authenticating with: %r" % authenticated)
                response = yield self.open(authenticated,
                        followRedirect = followRedirect,
                        proxy = proxy,
                        _redirectCount = _redirectCount+1,
                        **kw)

            else:
                log.msg("No {0} authenticator installed.".format(ur.scheme))
                raise ur

        else:
            log.msg("%r: response for %r: %r" % (self, request, response))
            response.verifyDigest()
            self.extractCookies(response)

        returnValue(response)


    def _supportedAuthenticationScheme(self, scheme, authenticator):
        if authenticator:
            schemes = authenticator.schemes
            log.debug("Supported auth schemes: {0}".format(", ".join(schemes)))
            for s in schemes:
                if s.upper() == scheme.upper():
                    return True
            log.debug("Unsupported auth scheme: {0}".format(scheme))
        else:
            log.debug("No authenticator installed")
        return False


    def _isSecureRequest(self, requester, authenticator):
        return bool(self.secure or requester.secure or authenticator.secure)


    _authHeader = "Authorization"

    def _buildAuthenticatedRequest(self, request, authorization):
        return request.copy(headers={self._authHeader:authorization})


    def extractCookies(self, response):
        log.msg("Extracting cookies: %r" % response, logLevel=log.DEBUG)
        assert response is not None
        self._cookieJar.extract_cookies(response, response.request)
        return response


    def getRequester(self, request, **kw):
        key = self._getRequesterKey(request)
        log.msg("Loading requester for: %s" % key, logLevel=log.DEBUG)

        if key in self._requesterCache:
            requester = self._requesterCache[key]
            log.msg("requester retrieved from cache: %s" % requester,
                    logLevel=log.DEBUG)

        elif len(self._requesterCache) == self.maxConnections:
            log.msg("cannot add %s: cache full" % request, logLevel=log.DEBUG)
            raise TooManyConnections(key)

        # Cache a new Requester

        elif request.proxy is not None:
            proxy.setRemote(request.host, request.port)
            requester = request.proxy
            # XXX reset timeout?

        else:
            if self._proxyer:
                proxy = self._proxyer.getRequester(request)
            else:
                proxy = None

            if proxy:
                log.debug("%r caching proxy %r from proxier %r" % (
                        self, proxy, self._proxyer))
                request.setProxy(proxy)
                proxy.setRemote(request.host, request.port)
                requester = self._requesterCache[key] = proxy

            else:
                requester = self._buildRequester(request, **kw)
                log.msg("%r caching %r" % (self, requester), logLevel=log.DEBUG)
                self._requesterCache[key] = requester

        log.msg("Requester cache: %s" % ", ".join(self._requesterCache.keys()),
                logLevel=log.DEBUG) 

        return requester


    def _getRequesterKey(self, request):
        return "%s://%s" % (request.url.scheme, request.url.netloc)


    def buildRequest(self, request, **kw):
        log.msg("Building a request: %s" % request, logLevel=log.DEBUG)
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
        log.msg("Creating a(n) %s requester" % scheme, logLevel=log.DEBUG)

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

