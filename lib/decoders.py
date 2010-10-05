from codecs import getincrementaldecoder as _getincrementaldecoder
from struct import calcsize, unpack, unpack_from, error as UnpackError
import gzip, zlib

from twisted.python import urlpath, util

from pendrell import log
from pendrell.util import CRLF



def getIncrementalDecoder(encoding):
    if encoding == "chunked":
        decoder = ChunkingIncrementalDecoder

    elif encoding == "deflate":
        decoder = ZlibIncrementalDecoder

    elif encoding == "gzip":
        decoder = GzipIncrementalDecoder

    else:
        decoder = codecs.getincrementaldecoder(encoding)

    return decoder

getincrementaldecoder = getIncrementalDecoder



def loadDecoders(encodings):
    decoders = list()

    for encoding in encodings:
        codecClass = getIncrementalDecoder(encoding)
        if codecClass is not None:
            codec = codecClass()
            decoders.append(codec)

    return decoders



_ZlibIncrementalDecoder = _getincrementaldecoder("zlib")

class ZlibIncrementalDecoder(_ZlibIncrementalDecoder):
    """Extends codec.ZlibIncrementalDecoder

    From http://zlib.net/zlib_faq.html:

    What's the difference between the "gzip" and "deflate" HTTP 1.1 encodings?

    "gzip" is the gzip format, and "deflate" is the zlib format. They should
    probably have called the second one "zlib" instead to avoid confusion with the
    raw deflate compressed data format. While the HTTP 1.1 RFC 2616 correctly points
    to the zlib specification in RFC 1950 for the "deflate" transfer encoding, there
    have been reports of servers and browsers that incorrectly produce or expect raw
    deflate data per the deflate specficiation in RFC 1951, most notably Microsoft.
    So even though the "deflate" transfer encoding using the zlib format would be
    the more efficient approach (and in fact exactly what the zlib format was
    designed for), using the "gzip" transfer encoding is probably more reliable due
    to an unfortunate choice of name on the part of the HTTP 1.1 authors.

    Bottom line: use the gzip format for HTTP 1.1 encoding.
    """

    def __init__(self):
        _ZlibIncrementalDecoder.__init__(self)
        self.decompressers = (
                zlib.decompressobj(-zlib.MAX_WBITS),
                self.decompressobj,
            )
        self.decompressobj = None


    def decode(self, input, final=False):
        decompressers = list(self.decompressers)
        decoded = None
        errors = list()
        while decompressers and decoded is None:
            decompresser = decompressers.pop()
            try:
                decoded = decompresser.decompress(input)
            except zlib.error, ze:
                errors.append((decompresser, ze))
                decoded = None
            else:
                self.__decompresser = decompresser

        if decoded is None:
            raise ze

        assert decompresser is not None
        # decompresser is the decompressor that actually worked.
        if final:
            decoded += decompresser.flush()

        return decoded


    def reset(self):
        _ZlibIncrementalDecoder.reset(self)
        self.decompressers = (
                self.decompressobj,
                zlib.decompressobj(-zlib.MAX_WBITS)
            )
        self.decompressobj = None



class GzipIncrementalDecoder(ZlibIncrementalDecoder):

    def __init__(self):
        ZlibIncrementalDecoder.__init__(self)
        # WBITS magic explained at:
        #   http://www.mail-archive.com/python-list@python.org/msg212566.html
        self.decompressobj = zlib.decompressobj(-zlib.MAX_WBITS)
        # Unfortunately we have to keep a buffer in order to ensure that we
        # catch the CRC32 and ISIZE values.
        self._buffer = str()
        self._readGzipHeader = False
        self._size = 0
        self._crc = zlib.crc32(str())


    def decode(self, data, final=False):
        data = self._buffer + data
        dataLen = len(data)
        self._buffer = None

        if self._readGzipHeader is not True:
            try:
                headerLen = self._decodeHeader(data)

            except UnpackError, ue:
                # Handled below
                assert self._readGzipHeader is False

            else:
                self._readGzipHeader = True
                data = data[headerLen:]
                dataLen -= headerLen

        if self._readGzipHeader and dataLen > self._footerLen:
            data, footer = data[:dataLen], data[dataLen:]
            dataLen -= self._footerLen

            decoded = ZlibIncrementalDecoder.decode(self, data, final)
            self._crc = zlib.crc32(decoded, self._crc)
            self._size += len(decoded)

            footer = self.decompressobj.unused_data + footer
            if final:
                ((crc, size), _) = self._decodeFooterValues(footer)
                if not crc == self._crc:
                    raise IOError("CRC check failed")
                elif not size == gzip.LOWU32(self._size):
                    raise IOError("Incorrect length of data produced")
                 
            else:
                self._buffer = footer

        else:
            decoded = str()
            self._buffer = data

        return decoded


    def reset(self):
        ZlibIncrementalDecoder.reset(self)
        self._crc = zlib.crc32(str())
        self._size = 0
        self._buffer = str()
        self._readGzipHeader = False


    # Modified from the gzip module:
    def _decodeHeader(self, buffer):
        assert isinstance(buffer, basestring)
        GZIP_MAGIC = hex(0x1f8b)

        preamble, offset = self._decodeHeaderPreamble(buffer)
        (magic, method, flag, mtime, extra, os) = preamble
        if hex(magic) != GZIP_MAGIC:
            raise IOError("Not gzip data")
        if method != 8:
            raise IOError("Unknown compression method: %r" % method)

        offset += self._decodeHeaderFields(flag, buffer[offset:])

        return offset


    @classmethod
    def _decodeHeaderFields(klass, flag, buffer):
        FTEXT, FHCRC, FEXTRA, FNAME, FCOMMENT = 1, 2, 4, 8, 16
        headerFields = (
                (FEXTRA, klass._decodeHeaderExtra),
                (FNAME, klass._decodeHeaderStringy),
                (FCOMMENT, klass._decodeHeaderStringy),
                (FHCRC, klass._decodeHeaderCRC16),
            )
        offset = 0
        for mask, decode in headerFields:
            if flag & mask:
                _, bytes = decode(buffer[offset:])
                offset += bytes
        return offset


    @staticmethod
    def _decodeHeaderPreamble(buffer):
        fmt = ">HBBIBB"
        bytes = calcsize(fmt)
        preamble = unpack_from(fmt, buffer, 0)
        return preamble, bytes


    @staticmethod
    def _decodeHeaderExtra(buffer):
        # Read & discard the extra field, if present
        # xlen is stored little-endian
        bytes = 0
        xlen = unpack_from(">H", buffer, extraLen)
        bytes += 2
        extra = unpack_from("%ds" % xlen, buffer, extraLen)
        bytes += xlen
        return extra, bytes


    @staticmethod
    def _decodeHeaderStringy(buffer):
        EOS = "\000"
        stringy = str()
        length = 0
        char = None
        while char != EOS:
            char = unpack_from("c", buffer, length)
            length += 1
            if char != EOS:
                stringy += char
        return stringy, length


    @staticmethod
    def _decodeHeaderCRC16(buffer):
        fmt = ">H"
        crc16 = unpack(fmt, buffer)
        return crc16, calcsize(fmt)


    _footerLen = calcsize("II")

    @staticmethod
    def _decodeFooterValues(footer):
        fmt = "II"
        (crc32, isize) = unpack(fmt, footer)
        return (crc32, isize), calcsize(fmt)




class ChunkingIncrementalDecoder(object):

    def __init__(self):
        self._buffer = str()
        self._chunkCount = long()
        self._chunk = None
        self._decodedLength = long()

        self.finished = False


    def reset(self):
        self._buffer = str()
        self._chunkCount = long()
        self._chunk = None
        self._decodedLength = long()

        self.finished = False


    def decode(self, raw, endChunking=False):
        self._buffer += raw

        content = str()
        chunking = True
        while chunking:
            try:
                chunk, raw = _Chunk.fromString(self._buffer)

            except _IncompleteChunk:
                chunking = False

            else:
                assert chunk.length >= 0

                if chunk.length == 0:
                    chunking = False
                    endChunking = True

                else:
                    content += chunk.content
                    self._decodedLength += chunk.length

                self._buffer = raw
                self._chunkCount += 1

        self.finished = endChunking

        return content


    def getExtra(self):
        if self.finished:
            return self._buffer



class _IncompleteChunk(Exception):
    pass


class _Chunk(object):

    def __init__(self, length, content):
        if len(content) != length:
            raise ValueError("Content %r is not %dB" % (content, length))
        self.length = long(length)
        self.content = content


    @classmethod
    def fromString(klass, raw):
        length, raw = klass._parseChunkLength(raw)
        content, raw = klass._parseChunk(length, raw)
        chunk = klass(length, content)
        return chunk, raw


    @classmethod
    def _parseChunkLength(klass, raw):
        """
        Returns:
            The chunk length as parsed.
        Postconditions:
            self._chunkLength is set to number of bytes to be read for this
            chunk, including the trailing CRLF.
        """
        hexLen, crlf, raw = raw.partition(CRLF)

        if not (len(hexLen) > 0 and crlf == CRLF):
            raise _IncompleteChunk(raw)

        # The buffer contains a hex-encoded chunk length followed by CRLF.
        try:
            length = int(hexLen, 16)

        except TypeError:
            raise ValueError("No chunk length specified: %r" % hexLen)

        if length < 0:
            raise ValueError("%r is not a positive integer" % (length))

        return length, raw


    @classmethod
    def _parseChunk(klass, length, raw):
        """
        Preconditions:
            self._chunkLength is set to number of bytes still to be read for
            this chunk.
        Returns:
            A 2-tuple (data, rawData) of strings, where 'data' is chunk-data and
            'rawData' is any data trailing the parsed data.  Either item may be
            an empty string.
        Postconditions:
            self._chunkLength is set to number of bytes still to be read for
            this chunk (and therefore may be 0).
        """
        if len(raw) < length + len(CRLF):
            raise _IncompleteChunk(length, raw)

        # The buffer contains the end of the current chunk, so parse the
        # chunk until the trailing CRLF and buffer the remaining data.
        chunk = raw[:length]

        raw = raw[length+len(CRLF):]

        return chunk, raw


__id__ = """$Id: agent.py 84 2010-06-01 16:01:45Z ver $"""[5:-2]

