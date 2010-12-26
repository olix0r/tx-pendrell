Pendrell:  Twisted HTTP/1.1 User Agent for the Programmable Web
---------------------------------------------------------------

Pendrell augments the twisted.web framework with an HTTP 1client that has
several advantages over prior art (or at least urllib2 and twisted.web.client):

  * HTTP 1.1 support:

    - TE/transfer-encoding support for chunked, gzip, and deflate encodings
    - Ability to simultaneously maintain multiple persistent connections.

  * Transparent gzip and deflate Content-encoding support.
  * Ability to stream data, by performing call-backs with data chunks,
    alleviates the need to buffer large files.

    - Advanced gzip support accommodates incremental decoding of chunked streams.

  * Asynchronous (twisted) API.
  * Integration with cookielib, and compatibility with urllib2.Request API.
  * Proxy Support.


Changelog
---------

Version 0.3.7
  * Make HTTP more less-noisy ;p

Version 0.3.6
  * Make HTTP less noisy.

Version 0.3.5
  * Typo fix in version compatibility

Version 0.3.4
  * Much less logging
  * Version compatibility object eliminates build-time requirements on Twisted

Version 0.3.3
  * LRU requester cache cleanup.

Version 0.3.2
  * Support servers that neither provide a content-length nor use chunked
    encoding.

Version 0.3.1
  * Authorization caching eliminates unnecessary unauthorized responses.

Version 0.3.0
  * Allow multiple Authenticators to be installed into Agent.authenticators.
  * Modify errors.UnauthorizedResponse to handle multiple WWW-Authenticate
    header values.


Contact
-------

Oliver Gould <ver at olix0r.net>
E242 A7F8 0901 CB63 EBA9  62EA 90F1 192F 0294 0825

http://pendrell.olix0r.net/
http://github.com/olix0r/tx-pendrell


License
-------

Copyright (c) 2010  Oliver V. Gould

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in all
  copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
