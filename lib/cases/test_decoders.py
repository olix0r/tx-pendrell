from twisted.trial.unittest import TestCase
from twisted.web import http

from pendrell import log

from pendrell.decoders import ChunkingIncrementalDecoder
from pendrell.util import b64random, normalizeBytes


class ChunkingIncrementalDecoderTest(TestCase):

    def setUp(self):
        self.chunker = c = ChunkingIncrementalDecoder()


    def test_decodeB8(self):
        original = b64random(8)

        chunk = str().join(http.toChunk(original))
        decoded = self.chunker.decode(chunk)

        self.assertEquals(original, decoded)


    def test_decodeKB8(self):
        original = b64random(normalizeBytes(8, "KB"))

        chunk = str().join(http.toChunk(original))
        decoded = self.chunker.decode(chunk)

        self.assertEquals(original, decoded)


    def test_decodeKB1x1B(self):
        original = b64random(normalizeBytes(1, "KB"))

        chunk = str().join(http.toChunk(original))
        decoded = ""
        for char in chunk[:]:
            decoded += self.chunker.decode(char)

        self.assertEquals(original, decoded)


    def test_decode2xKB1(self):
        original = b64random(normalizeBytes(1, "KB"))

        chunk = str().join(http.toChunk(original))
        nullChunk = str().join(http.toChunk(""))

        data = chunk + nullChunk + chunk
        decoded = self.chunker.decode(data)

        self.assertTrue(self.chunker.finished)
        extra = self.chunker.getExtra()

        self.assertEquals(original, decoded)

        self.assertEquals(len(chunk), len(extra))
        self.assertEquals(chunk, extra)


