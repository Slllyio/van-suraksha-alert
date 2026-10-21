"""Network settings for the cloud readers (cloud_hls, cloud_modis). Call setup() before GDAL or curl first read their config.

- In a cloud session, a proxy re-signs TLS (CA bundle below) and adds the NASA Earthdata secret to *.nasa.gov calls.
- On a server there is neither: the system CA store applies, and EARTHDATA_TOKEN (an Earthdata bearer token, set in the
  server's .env) is sent on NASA calls instead. A custom Authorization header is dropped by curl on a redirect to another
  host, so the S3 links LP DAAC redirects to do not receive it."""
import os

CA = "/root/.ccr/ca-bundle.crt"


def setup():
    if os.path.exists(CA):
        for k in ("CURL_CA_BUNDLE", "GDAL_CURL_CA_BUNDLE"):
            os.environ.setdefault(k, CA)
    if os.environ.get("EARTHDATA_TOKEN"):
        os.environ["GDAL_HTTP_HEADERS"] = "Authorization: Bearer " + os.environ["EARTHDATA_TOKEN"]
    for k in ("GDAL_HTTP_COOKIEFILE", "GDAL_HTTP_COOKIEJAR"):
        os.environ.setdefault(k, "/tmp/gdal_cookies.txt")


def headers():
    """Headers for requests calls to NASA hosts."""
    t = os.environ.get("EARTHDATA_TOKEN")
    return {"Authorization": "Bearer " + t} if t else {}
