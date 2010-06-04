import base64
from hashlib import md5

from twisted.web.resource import Resource
from twisted.web.server import Site

from pendrell import log
from pendrell.util import humanizeBytes, normalizeBytes


class MD5Root(Resource):

    isLeaf = False

    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        if name.lower() == "valid":
            child = ValidMD5()
        elif name.lower() == "invalid":
            child = InvalidMD5()
        else:
            child = Resource.getChild(self, name, request)

        return child



class ValidMD5(Resource):
    
    isLeaf = True

    def render_GET(self, request):
        content = "Joy is a good doggy.\n"
        digest = base64.b64encode(md5(content).digest())
        request.setHeader("Content-MD5", digest)
        return content


class InvalidMD5(Resource):
    
    isLeaf = True

    def render_GET(self, request):
        content = "Joy is a good doggy.\n"
        invalidContent = "Joy is a bad doggy.\n"

        digest = base64.b64encode(md5(invalidContent).digest())
        request.setHeader("Content-MD5", digest)

        return content



class MD5Site(Site):

    def __init__(self):
        Site.__init__(self, MD5Root())


