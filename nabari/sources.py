"""The collector accepts only these two public, official sources."""
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    origin: str
    listing: str
    hosts: tuple[str, ...]
    evergreen: tuple[str, ...] = ()


SOURCES = {
    "city": Source("city", "名張市役所", "https://www.city.nabari.lg.jp",
        "https://www.city.nabari.lg.jp/news.html", ("www.city.nabari.lg.jp",), (
            "/s020/030/010/004/20210323144609.html",
            "/s020/030/010/004/20210323104524.html",
            "/s020/030/010/004/20210322105019.html",
            "/s031/090/180/370/201502052102.html",
            "/s079/000/020/20210308105824.html",
            "/s002/020/010/030/230/201502050148.html",
            "/map/map/n0000/n0000.html",
        )),
    "tourism": Source("tourism", "名張市観光協会", "https://kankou-nabari.jp",
        "https://kankou-nabari.jp/news", ("kankou-nabari.jp", "www.kankou-nabari.jp")),
}

CATEGORIES = {
    "event": "イベント", "tourism": "観光・お出かけ", "waste": "ごみ・資源",
    "health": "健康・福祉", "consult": "相談", "disaster": "防災", "city": "くらし・手続き",
}


def safe_url(value: str, source: Source, base: str | None = None) -> str:
    """No arbitrary host, userinfo, non-HTTPS URL, port, or query is fetched."""
    url = urljoin(base or source.origin + "/", value)
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or p.hostname not in source.hosts or p.username or p.password
                or p.port not in (None, 443) or p.query or "\\" in url
                or any(ord(c) < 32 for c in url)):
            raise ValueError("許可されていない取得先です")
    except (ValueError, TypeError) as exc:
        raise ValueError("許可されていない取得先です") from exc
    # Collapse www on the tourism domain for a stable duplicate key.
    host = "kankou-nabari.jp" if source.key == "tourism" else p.hostname
    return urlunsplit(("https", host, p.path or "/", "", ""))
