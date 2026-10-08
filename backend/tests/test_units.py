import httpx
import pytest

from app.services.pagespeed import PageSpeedError, PageSpeedService, normalize
from app.urls import InvalidUrl, validate_and_normalize
from tests.conftest import FakePSI, lighthouse_payload


# ---- URL validation ---------------------------------------------------------------
@pytest.mark.parametrize("url,clean,key", [
    ("https://Example.com", "https://example.com/", "example.com/"),
    ("https://example.com/courses/", "https://example.com/courses/", "example.com/courses"),
    ("http://example.com:80/a?b=1#frag", "http://example.com/a?b=1", "example.com/a?b=1"),
    ("https://sub.example.co.in:8443/x", "https://sub.example.co.in:8443/x", "sub.example.co.in:8443/x"),
])
def test_url_normalisation(url, clean, key):
    assert validate_and_normalize(url) == (clean, key)


def test_duplicate_keys_ignore_scheme_and_trailing_slash():
    assert validate_and_normalize("http://example.com/a/")[1] == validate_and_normalize("https://example.com/a")[1]


@pytest.mark.parametrize("bad", ["", "example.com", "ftp://example.com", "https://localhost/", "http://127.0.0.1",
                                 "https://10.0.0.5/x", "https://user:pw@example.com", "https://exa mple.com",
                                 "https://-bad-.com", "javascript:alert(1)", "https://intranet"])
def test_url_rejected(bad):
    with pytest.raises(InvalidUrl):
        validate_and_normalize(bad)


# ---- PageSpeed normalisation ----------------------------------------------------------
def test_normalize_full():
    r = normalize(lighthouse_payload("https://example.com/", "mobile", 87), "https://example.com/", "mobile")
    assert r["performance_score"] == 87 and r["accessibility_score"] == 95
    assert r["fcp"] == 1.8 and r["lcp"] == 2.91 and r["tbt"] == 310 and r["cls"] == 0.081
    assert r["speed_index"] == 3.2 and r["strategy"] == "mobile" and r["final_url"] == "https://example.com/"


def test_normalize_missing_metrics_are_none():
    data = lighthouse_payload("https://e.com/", "desktop", 90, missing=("largest-contentful-paint", "speed-index"))
    data["lighthouseResult"]["categories"].pop("seo")
    r = normalize(data, "https://e.com/", "desktop")
    assert r["lcp"] is None and r["speed_index"] is None and r["seo_score"] is None and r["fcp"] == 1.8


def test_normalize_runtime_error_and_missing_score():
    data = {"lighthouseResult": {"runtimeError": {"code": "FAILED_DOCUMENT_REQUEST", "message": "net::ERR_X"}}}
    with pytest.raises(PageSpeedError) as e:
        normalize(data, "u", "mobile")
    assert e.value.code == "website_unavailable"
    with pytest.raises(PageSpeedError) as e:
        normalize(lighthouse_payload("u", "mobile", None), "u", "mobile")
    assert e.value.code == "missing_metrics"
    with pytest.raises(PageSpeedError):
        normalize({}, "u", "mobile")


async def test_retry_then_success():
    psi = FakePSI()
    psi.scores[("https://e.com/", "mobile")] = [("http", 503, {"error": {"message": "Backend Error"}}),
                                                ("timeout",), 77]
    svc = PageSpeedService(psi.client(), sleep=_nosleep)
    r = await svc.run("https://e.com/", "mobile")
    assert r["performance_score"] == 77 and len(psi.calls) == 3


async def test_quota_exceeded_is_not_retried_and_key_is_scrubbed():
    psi = FakePSI()
    body = {"error": {"code": 429, "message": "Quota exceeded for quota metric 'Queries' and limit 'Queries per day' "
                                              "key=TEST-PSI-KEY-123", "errors": [{"reason": "rateLimitExceeded"}]}}
    psi.scores[("https://e.com/", "desktop")] = ("http", 429, body)
    svc = PageSpeedService(psi.client(), sleep=_nosleep)
    with pytest.raises(PageSpeedError) as e:
        await svc.run("https://e.com/", "desktop")
    assert e.value.code == "quota_exceeded" and len(psi.calls) == 1
    assert "TEST-PSI-KEY-123" not in e.value.message


async def test_rate_limit_retried_and_invalid_key_not():
    psi = FakePSI()
    psi.scores[("https://e.com/", "desktop")] = [("http", 429, {"error": {"message": "Rate Limit Exceeded"}}), 91]
    svc = PageSpeedService(psi.client(), sleep=_nosleep)
    assert (await svc.run("https://e.com/", "desktop"))["performance_score"] == 91
    psi.scores[("https://e.com/", "mobile")] = ("http", 400, {"error": {"message": "API key not valid. Please pass a valid API key.", "errors": [{"reason": "badRequest"}], "details": [{"reason": "API_KEY_INVALID"}]}})
    with pytest.raises(PageSpeedError) as e:
        await svc.run("https://e.com/", "mobile")
    assert e.value.code == "api_key_invalid" and len(psi.calls) == 3  # 2 desktop + 1 mobile (not retried)


async def test_unreachable_site_from_api_500():
    psi = FakePSI()
    psi.scores[("https://down.example.com/", "mobile")] = (
        "http", 500, {"error": {"message": "Lighthouse returned error: FAILED_DOCUMENT_REQUEST. Lighthouse was unable to reliably load the page"}})
    svc = PageSpeedService(psi.client(), sleep=_nosleep)
    with pytest.raises(PageSpeedError) as e:
        await svc.run("https://down.example.com/", "mobile")
    assert e.value.code == "website_unavailable" and len(psi.calls) == 1


async def test_network_error():
    def boom(request):
        raise httpx.ConnectError("connection refused", request=request)

    svc = PageSpeedService(httpx.AsyncClient(transport=httpx.MockTransport(boom)), sleep=_nosleep)
    with pytest.raises(PageSpeedError) as e:
        await svc.run("https://e.com/", "mobile")
    assert e.value.code == "network_error"


async def _nosleep(_):
    return None
