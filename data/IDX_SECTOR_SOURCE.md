# Sector classification provenance

The initial cache is a minimal derivative of IDX company-profile records mirrored in
[markusprap/idx-bei-stock-analysis](https://github.com/markusprap/idx-bei-stock-analysis),
commit 6631bea72720c4451ec8486c1e2c002081f315f5 (2026-02-03).
Only public company name, ticker and IDX-IC sector are retained.
The cache is dated; unknown tickers are NOT inferred from names or price behavior.
The rotation job attempts refresh from the public IDX endpoint weekly. Failure uses
this explicitly dated cache, with source status visible in the UI.

Upstream license:

MIT License

Copyright (c) 2024

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
