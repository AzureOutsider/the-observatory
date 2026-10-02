from datetime import datetime, timedelta

from app.models import NewsItem
from app.services import news
from app.services.news import (
    _fetch_federal_reserve,
    _published_at,
    fetch_news,
    prune_old_news,
)


def test_fetch_news_normalises_and_deduplicates_sources(session, monkeypatch):
    # Fixtures use fixed 2026-08-31 publish dates; retention pruning is
    # covered by its own test and is irrelevant to normalization/dedupe.
    monkeypatch.setattr(news, "prune_old_news", lambda session: 0)
    monkeypatch.setattr(
        news,
        "SOURCE_FETCHERS",
        {
            "sina": lambda limit: [
                {"title": "政策发布，人工智能产业获支持", "url": "https://sina.test/1", "ctime": "2026-08-31 10:00:00"}
            ],
            "wallstreetcn": lambda limit: [
                {"title": "政策发布，人工智能产业获支持", "content_text": "重复报道", "display_time": "2026-08-31 10:01:00"},
                {"title": "黄金价格震荡", "content_text": "黄金市场午后变化", "display_time": "2026-08-31 10:02:00"},
            ],
        },
    )

    rows = fetch_news(limit=10, session=session, refresh=True)

    assert len(rows) == 2
    assert rows[0]["importance"] == 5
    assert rows[0]["source_label"] in {"新浪财经", "华尔街见闻"}
    assert rows[0]["fetched_at"]
    assert session.query(NewsItem).count() == 2


def test_fetch_news_reads_fresh_cache_without_upstream_request(session, monkeypatch):
    monkeypatch.setattr(news, "SOURCE_FETCHERS", {"sina": lambda limit: [{"title": "缓存测试新闻"}]})
    first = fetch_news(limit=5, session=session, refresh=True)
    monkeypatch.setattr(news, "SOURCE_FETCHERS", {"sina": lambda limit: (_ for _ in ()).throw(AssertionError("should use cache"))})

    second = fetch_news(limit=5, session=session)

    assert second[0]["title"] == first[0]["title"]


def test_fetch_news_returns_stale_cache_when_refresh_fails(session, monkeypatch):
    old = datetime.now() - timedelta(hours=3)
    session.add(NewsItem(title="旧新闻", source="sina", fetched_at=old, importance=3, quality="headline_only"))
    session.commit()
    monkeypatch.setattr(news, "SOURCE_FETCHERS", {"sina": lambda limit: (_ for _ in ()).throw(OSError("offline"))})

    rows = fetch_news(limit=5, session=session, refresh=True)

    assert rows[0]["title"] == "旧新闻"
    assert rows[0]["quality"] == "stale"


def test_prune_old_news_deletes_items_older_than_retention(session):
    now = datetime.now()
    session.add_all(
        [
            NewsItem(
                title="旧新闻",
                source="sina",
                published_at=now - timedelta(days=8),
                fetched_at=now - timedelta(days=8),
                importance=3,
                quality="full",
            ),
            NewsItem(
                title="新新闻",
                source="sina",
                published_at=now - timedelta(days=2),
                fetched_at=now - timedelta(days=2),
                importance=3,
                quality="full",
            ),
            # Headline-only item without publish time: age falls back to fetched_at.
            NewsItem(
                title="无发布时间旧新闻",
                source="sina",
                published_at=None,
                fetched_at=now - timedelta(days=10),
                importance=2,
                quality="headline_only",
            ),
            NewsItem(
                title="无发布时间新新闻",
                source="sina",
                published_at=None,
                fetched_at=now - timedelta(hours=1),
                importance=2,
                quality="headline_only",
            ),
        ]
    )
    session.commit()

    deleted = prune_old_news(session, retention_days=7)

    assert deleted == 2
    remaining = {item.title for item in session.query(NewsItem).all()}
    assert remaining == {"新新闻", "无发布时间新新闻"}


def test_prune_old_news_with_non_positive_retention_is_noop(session):
    session.add(
        NewsItem(
            title="很旧的新闻",
            source="sina",
            published_at=datetime.now() - timedelta(days=365),
            fetched_at=datetime.now() - timedelta(days=365),
            importance=3,
            quality="full",
        )
    )
    session.commit()

    assert prune_old_news(session, retention_days=0) == 0
    assert session.query(NewsItem).count() == 1


def test_published_at_parses_rfc822_and_epoch_values():
    assert _published_at({"pubDate": "Mon, 31 Aug 2026 13:00:00 GMT"}) == datetime(2026, 8, 31, 13, 0)
    assert _published_at({"ctime": "1788180948"}) is not None


def test_federal_reserve_adapter_reads_rss(monkeypatch):
    rss = """<rss><channel><item><title>Policy statement</title><link>https://fed.test/1</link><description>Rates remain unchanged.</description><pubDate>Mon, 31 Aug 2026 13:00:00 GMT</pubDate></item></channel></rss>"""

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return rss.encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())

    rows = _fetch_federal_reserve(3)

    assert rows[0]["title"] == "Policy statement"
    assert rows[0]["pubDate"].endswith("GMT")
