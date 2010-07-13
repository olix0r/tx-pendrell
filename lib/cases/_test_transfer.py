from twisted.internet.defer import DeferredList, inlineCallbacks, returnValue
from twisted.python import log
from twisted.trial.unittest import TestCase

from pendrell import messages
from pendrell.cases.junk_server import JunkSiteTestMixin
from pendrell.cases.util import PendrellTestMixin


class _Response(messages.Response):
    def __init__(self, *args, **kw):
        messages.Response.__init__(self, *args, **kw)
        self.count = long()
    def __len__(self):
        return self.count
    def handleData(self, data):
        self.count += len(data)


class _Request(messages.Request):
    responseClass = _Response




class TransferTestMixin(JunkSiteTestMixin):

    chunkSize = 8 * 1024
    timeout = 300

    def test_0001xB000(self):
        return self._test_getJunk(0, "B")

    def test_0001xKB001(self):
        return self._test_getJunk(1, "KB")

    def test_0001xMB001(self):
        return self._test_getJunk(1, "MB")

    def test_0002xKB001(self):
        return self._test_getJunks(2, 1, "KB")

    def test_0002xMB001(self):
        return self._test_getJunks(2, 1, "MB")

    def test_0128xKB001(self):
        return self._test_getJunks(128, 1, "KB")



class ParallelTransferTestMixin(JunkSiteTestMixin):

    chunkSize = 1024

    largeSize = (64, "KB")

    manyCount = 64
    manySize = (1, "KB")

    timeout = 60

    def setUp(self):
        JunkSiteTestMixin.setUp(self)
        self.manyCompleted = 0


    def getMany(self):
        assert self.manyCount >= 0
        return self._test_getJunks(self.manyCount, *self.manySize)


    @inlineCallbacks
    def _test_getJunk(self, size, suffix):
        r = yield JunkSiteTestMixin._test_getJunk(self, size, suffix)
        self.manyCompleted += 1
        returnValue(r)


    @inlineCallbacks
    def getLarge(self):
        yield self._test_getJunk(*self.largeSize)

        manyCompleted = self.manyCompleted - 1  # Don't count the Large
        self.assertTrue(0.95*self.manyCount < manyCompleted <= self.manyCount)


    def test_64x1KB_while_1x64KB(self):
        many = self.getMany()
        large = self.getLarge()
        return DeferredList([many, large])



class XLTransferTestMixin(JunkSiteTestMixin):

    chunkSize = 64 * 1024  # Try 64k chunks
    timeout = 30 * 60  # Let this run for up to an hour (!)


    def test_0512xKB001(self):
        return self._test_getJunks(512, 1, "KB")

    def test_0002xGB1(self):
        return self._test_getJunks(2, 1, "GB")



class XXLTransferTestMixin(JunkSiteTestMixin):

    chunkSize = 64 * 1024  # Try 64k chunks
    timeout = 45 * 60  # Let this run for up to an hour (!)

    def test_0001xGB4(self):
        return self._test_getJunk(4, "GB")

    def test_1024xMB001(self):
        return self._test_getJunks(1024, 1, "MB")



class TransferTest(PendrellTestMixin, TransferTestMixin, TestCase):

    timeout = TransferTestMixin.timeout

    def setUp(self):
        PendrellTestMixin.setUp(self)
        TransferTestMixin.setUp(self)

    @inlineCallbacks
    def tearDown(self):
        yield TransferTestMixin.tearDown(self)
        yield PendrellTestMixin.tearDown(self)

    def getPage(self, url):
        return PendrellTestMixin.getPage(self, _Request(url))
        


class ParallelTransferTest(PendrellTestMixin, ParallelTransferTestMixin,
        TestCase):

    timeout = ParallelTransferTestMixin.timeout

    def setUp(self):
        PendrellTestMixin.setUp(self)
        ParallelTransferTestMixin.setUp(self)

    @inlineCallbacks
    def tearDown(self):
        yield ParallelTransferTestMixin.tearDown(self)
        yield PendrellTestMixin.tearDown(self)


    def getPage(self, url):
        request = _Request(url)
        return PendrellTestMixin.getPage(self, request)
        


class XLTransferTest(PendrellTestMixin, XLTransferTestMixin, TestCase):

    timeout = XLTransferTestMixin.timeout

    def setUp(self):
        PendrellTestMixin.setUp(self)
        XLTransferTestMixin.setUp(self)

    @inlineCallbacks
    def tearDown(self):
        yield XLTransferTestMixin.tearDown(self)
        yield PendrellTestMixin.tearDown(self)


    def getPage(self, url):
        return PendrellTestMixin.getPage(self, _Request(url))
        


class XXLTransferTest(PendrellTestMixin, XXLTransferTestMixin, TestCase):

    timeout = XXLTransferTestMixin.timeout

    def setUp(self):
        PendrellTestMixin.setUp(self)
        XXLTransferTestMixin.setUp(self)

    @inlineCallbacks
    def tearDown(self):
        yield XXLTransferTestMixin.tearDown(self)
        yield PendrellTestMixin.tearDown(self)


    def getPage(self, url):
        return PendrellTestMixin.getPage(self, _Request(url))
        


