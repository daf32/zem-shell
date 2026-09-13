"""`check_url`: what `hints install` and `theme install` may fetch from."""

import pytest

from zem.utils.net import UnsafeURL, check_url


@pytest.mark.parametrize("url", [
    "https://example.test/x.json",
    "https://example.test:8443/x.json",
    "http://localhost:8000/x.json",
    "http://127.0.0.1/x.json",
    "http://[::1]/x.json",
])
def test_accepted(url):
    check_url(url)


@pytest.mark.parametrize("url", [
    "http://example.test/x.json",
    "http://localhost.evil.test/x.json",
    "file:///etc/passwd",
    "ftp://example.test/x.json",
    "https:///no-host",
    "example.test/x.json",
])
def test_refused(url):
    with pytest.raises(UnsafeURL):
        check_url(url)
