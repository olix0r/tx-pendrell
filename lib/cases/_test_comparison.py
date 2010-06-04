from urllib2 import urlopen

from twisted.internet import reactor
from twisted.internet.defer import (
        DeferredList, maybeDeferred,
        inlineCallbacks, returnValue)
from twisted.internet.threads import deferToThread
from twisted.trial.unittest import TestCase
from twisted.web.client import getPage as tx_getPage

from pendrell import log
from pendrell.cases.test_agent import PendrellTestMixin
from pendrell.cases._test_transfer import (TransferTestMixin,
        XLTransferTestMixin)



class Urllib2TestMixin(object):


    def getPages(self, count, url):
        pages = list()
        for i in xrange(0, count):
            page = self.getPage(url)
            pages.append(page)
        return pages

    def getPage(self, url):
        log.msg("Opening url: %r" % url)
        rsp = urlopen(url)
        return rsp.read()

    @inlineCallbacks
    def getPageLength(self, url):
        response = yield self.getPage(url)
        returnValue(len(response))



class ThreadedUrllib2TestMixin(object):

    def setUp(self):
        pass

    def tearDown(self):
        pass


    @inlineCallbacks
    def getPages(self, count, url):
        pages = list()

        for i in xrange(0, count):
            page = yield self.getPage(url)
            pages.append(page)

        returnValue(pages)


    def getPage(self, url):
        return deferToThread(self._openPage, url)

    def _openPage(self, url):
        log.msg("Opening url: %r" % url)
        rsp = urlopen(url)
        return rsp.read()


    @inlineCallbacks
    def getPageLength(self, url):
        response = yield self.getPage(url)
        returnValue(len(response))




class TwistedWebTestMixin(object):

    def setUp(self):
        pass

    def tearDown(self):
        pass


    def getPages(self, count, url):
        ds = list()
        for i in xrange(0, count):
            d = self.getPage(url)
            ds.append(d)
        return DeferredList(ds)


    def getPage(self, url):
        return tx_getPage(url)


    @inlineCallbacks
    def getPageLength(self, url):
        response = yield self.getPage(url)
        returnValue(len(response))



class TwistedWebTransferTest(TransferTestMixin, TwistedWebTestMixin, TestCase):
    timeout = 300

class ThreadedUrllib2TransferTest(TransferTestMixin, ThreadedUrllib2TestMixin,
        TestCase):
    timeout = 300


#class Urllib2TransferTest(TransferTestMixin, Urllib2TestMixin, TestCase):
#    pass
#


