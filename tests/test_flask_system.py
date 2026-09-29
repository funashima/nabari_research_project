"""Synthetic fixtures exercise the live Flask pipeline without network access."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from bs4 import BeautifulSoup

from nabari import create_app
from nabari.collector import CollectionError, PublicClient, acquire_run, collect_source, parse_article, parse_date, parse_listing
from nabari.db import connect, export_snapshot, import_snapshot, init_db, save_article, utc_now
from nabari.sources import SOURCES, safe_url

CITY_URL = SOURCES['city'].origin + '/s001/test.html'
TOURISM_URL = SOURCES['tourism'].origin + '/news/test'


def city_html(title='ごみ収集のお知らせ', body='出し方は公式ページで確認してください。', date='2026年9月20日'):
    return f'<article class="article"><h1>{title}</h1><p class="right">更新日：{date}</p><div class="txtbox">{body}</div></article>'


def tourism_html(title='名張の秋祭り', body='地域のお祭りの案内です。', date='2026-09-09T09:00:00+09:00'):
    return f'<article class="news-post"><h1 class="wp-entry-title">{title}</h1><time datetime="{date}">2026年9月9日</time><div class="wp-entry-content">{body}</div></article>'


class FakeClient:
    def __init__(self, source='city', fail=None, body=None):
        self.source = SOURCES[source]
        self.fail = fail
        self.body = body or (city_html() if source == 'city' else tourism_html())
        self.called = []
        self.prepared = False
        self.closed = False

    def prepare(self):
        self.prepared = True

    def html(self, url):
        assert self.prepared
        self.called.append(url)
        if url == self.source.listing:
            if self.fail == 'listing':
                raise CollectionError('network_error')
            if self.source.key == 'city':
                return '<dl class="news"><dd><a href="/s001/test.html">記事</a></dd></dl>', url
            return '<article class="news-list-item"><h2><a href="/news/test">記事</a></h2></article>', url
        if self.fail == 'article':
            raise CollectionError('network_error')
        return self.body, url

    def close(self):
        self.closed = True


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / 'test.sqlite3')
    init_db(path)
    return path


def seed(path, source='city', url=None, title=None, date=None):
    url = url or (CITY_URL if source == 'city' else TOURISM_URL)
    html = city_html(title or 'ごみ収集のお知らせ') if source == 'city' else tourism_html(title or '名張の秋祭り')
    article = parse_article(html, url, SOURCES[source])
    if date:
        article['source_date'] = date
    db = connect(path)
    try:
        save_article(db, article, utc_now())
    finally:
        db.close()


def rewind(path):
    db = connect(path)
    db.execute("UPDATE collection_runs SET finished_at=?", ((datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),))
    db.commit()
    db.close()


@pytest.fixture
def app(db_path):
    return create_app({'TESTING': True, 'DATABASE': db_path})


@pytest.mark.parametrize('value', ['http://www.city.nabari.lg.jp/a', 'https://evil.test/a', '//127.0.0.1/a',
    'https://www.city.nabari.lg.jp.evil.test/a', 'https://user@www.city.nabari.lg.jp/a',
    'https://www.city.nabari.lg.jp:444/a', 'https://www.city.nabari.lg.jp/a?next=evil', 'javascript:alert(1)'])
def test_unsafe_fetch_targets_rejected(value):
    with pytest.raises(ValueError):
        safe_url(value, SOURCES['city'])


def test_tourism_alias_and_fragments_have_one_canonical_url():
    assert safe_url('https://www.kankou-nabari.jp/news/test#x', SOURCES['tourism']) == TOURISM_URL


def test_real_source_structures_parse_without_navigation_or_scripts():
    a = parse_article(city_html(body='案内<script>alert(1)</script><form>フォーム</form>です'), CITY_URL, SOURCES['city'])
    b = parse_article(tourism_html(), TOURISM_URL, SOURCES['tourism'])
    assert a['source_date'] == '2026-09-20' and a['date_kind'] == 'updated'
    assert b['source_date'] == '2026-09-09' and b['date_kind'] == 'published'
    assert a['category'] == 'waste' and b['category'] == 'tourism'
    assert 'alert' not in a['excerpt'] and 'フォーム' not in a['excerpt']


def test_content_hash_detects_changes_beyond_excerpt():
    a = parse_article(city_html(body='前' * 220 + 'A'), CITY_URL, SOURCES['city'])
    b = parse_article(city_html(body='前' * 220 + 'B'), CITY_URL, SOURCES['city'])
    assert a['excerpt'] == b['excerpt'] and len(a['excerpt']) == 181
    assert a['content_hash'] != b['content_hash']


def test_listing_deduplicates_and_filters_external_links():
    html = '<div class="news-list-item"><h2><a href="/news/test#x">1</a><a href="/news/test">2</a><a href="https://evil.test/a">3</a></h2></div>'
    assert parse_listing(html, SOURCES['tourism']) == [TOURISM_URL]


def test_changed_source_structure_fails_explicitly():
    with pytest.raises(CollectionError, match='listing_structure_changed'):
        parse_listing('<p>サイト工事中</p>', SOURCES['city'])
    with pytest.raises(CollectionError, match='article_structure_changed'):
        parse_article('<h1>工事中</h1>', CITY_URL, SOURCES['city'])
    assert parse_date('2026年2月30日') is None


def test_collect_both_sources_persist_and_repeated_collection_is_idempotent(db_path):
    a = collect_source(db_path, 'city', client=FakeClient())
    b = collect_source(db_path, 'tourism', client=FakeClient('tourism'))
    assert (a['new'], b['new']) == (8, 1)  # city list + 7 evergreen pages
    rewind(db_path)
    c = collect_source(db_path, 'tourism', client=FakeClient('tourism'))
    assert c['new'] == 0 and c['unchanged'] == 1
    db = connect(db_path)
    assert db.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 9
    assert db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 9
    db.close()


def test_changed_article_creates_new_revision_preserving_first_seen(db_path):
    collect_source(db_path, 'tourism', client=FakeClient('tourism'))
    db = connect(db_path)
    original = dict(db.execute('SELECT * FROM articles').fetchone())
    db.close()
    rewind(db_path)
    result = collect_source(db_path, 'tourism', client=FakeClient('tourism', body=tourism_html(body='内容を変更しました')))
    db = connect(db_path)
    current = dict(db.execute('SELECT * FROM articles').fetchone())
    assert result['updated'] == 1 and current['revision'] == 2
    assert current['first_seen_at'] == original['first_seen_at']
    assert db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0] == 2
    db.close()


@pytest.mark.parametrize('where', ['listing', 'article'])
def test_network_failure_keeps_existing_articles_and_records_failure(db_path, where):
    seed(db_path, 'tourism')
    result = collect_source(db_path, 'tourism', client=FakeClient('tourism', fail=where))
    assert result['status'] == 'failed' and result['errors']
    db = connect(db_path)
    assert db.execute('SELECT COUNT(*) FROM articles').fetchone()[0] == 1
    assert db.execute('SELECT status FROM collection_runs').fetchone()[0] == 'failed'
    db.close()


def test_concurrent_collectors_and_cooldown_are_suppressed(db_path):
    db = connect(db_path)
    now = datetime.now(timezone.utc)
    first = acquire_run(db, 'city', now)
    second = acquire_run(db, 'city', now)
    assert first and second is None
    db.close()
    collect_source(db_path, 'tourism', client=FakeClient('tourism'))
    client = FakeClient('tourism')
    assert collect_source(db_path, 'tourism', client=client)['status'] == 'skipped'
    assert not client.called


def test_interrupted_run_is_marked_failed_and_recoverable(db_path):
    db = connect(db_path)
    acquire_run(db, 'city', datetime.now(timezone.utc) - timedelta(hours=1))
    # Recovery records the interruption; the cooldown then defers a new crawl.
    assert acquire_run(db, 'city', datetime.now(timezone.utc)) is None
    assert db.execute('SELECT status FROM collection_runs').fetchone()[0] == 'failed'
    db.close()


def test_flask_renders_both_sources_search_and_details_without_js(app, db_path):
    seed(db_path)
    seed(db_path, 'tourism')
    client = app.test_client()
    response = client.get('/')
    soup = BeautifulSoup(response.data, 'html.parser')
    assert response.status_code == 200 and len(soup.select('.card')) == 2
    assert soup.select_one('form[method=get]')
    api = client.get('/api/articles?source=tourism').json
    assert api['total'] == 1 and api['items'][0]['source_name'] == '名張市観光協会'
    assert client.get('/api/articles?q=ゴミ').json['total'] == 1
    article_id = api['items'][0]['id']
    detail = client.get('/articles/' + article_id)
    assert '掲載日' in detail.get_data(as_text=True) and TOURISM_URL in detail.get_data(as_text=True)
    assert client.get('/status').status_code == 200
    assert client.get('/about').status_code == 200
    assert client.get('/healthz').json['status'] == 'ok'
    assert 'nosniff' == response.headers['X-Content-Type-Options']


def test_future_publication_is_hidden_from_list_api_and_detail(app, db_path):
    seed(db_path, 'tourism', date='2099-10-01')
    client = app.test_client()
    assert client.get('/api/articles').json['total'] == 0
    article_id = hashlib.sha256(TOURISM_URL.encode()).hexdigest()[:24]
    assert client.get('/articles/' + article_id).status_code == 404
    assert client.get('/api/collection-status').json['sources'][1]['future'] == 1


def test_escaped_source_content_and_safe_search_parameters(app, db_path):
    seed(db_path, title='&lt;img src=x onerror=alert(1)&gt; ごみ')
    client = app.test_client()
    html = client.get('/').get_data(as_text=True)
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert BeautifulSoup(html, 'html.parser').select_one('img') is None
    assert client.get('/api/articles?q=%25').json['total'] == 0
    assert client.get('/api/articles?q=%27+OR+1=1--').json['total'] == 0
    assert client.get('/?source=not-real').status_code == 400
    assert client.get('/?page=abc').status_code == 400
    assert client.post('/api/collection-status').status_code == 405


def test_pagination_and_database_survive_app_restart(app, db_path):
    for i in range(14):
        seed(db_path, url=SOURCES['city'].origin + f'/s001/page{i}.html', title=f'案内{i:02}')
    restarted = create_app({'TESTING': True, 'DATABASE': db_path})
    api = restarted.test_client().get('/api/articles?page=2').json
    assert api['total'] == 14 and len(api['items']) == 2 and api['pages'] == 2


def test_export_import_is_explicit_dated_and_refuses_overwrite(db_path, tmp_path):
    seed(db_path)
    export = tmp_path / 'snapshot.json'
    export_snapshot(db_path, export)
    other = str(tmp_path / 'demo.sqlite3')
    init_db(other)
    assert import_snapshot(other, export) == 1
    with pytest.raises(ValueError, match='データのある'):
        import_snapshot(other, export)


def test_fixed_research_ui_and_data_are_served_but_not_database(app):
    client = app.test_client()
    assert client.get('/research/').status_code == 200
    assert len(client.get('/research/data/information.json').json['items']) == 10
    assert client.get('/research/../instance/nabari.sqlite3').status_code == 404


class Response:
    def __init__(self, status=200, data=b'', headers=None):
        self.status_code = status
        self.data = data
        self.headers = headers or {'Content-Type': 'text/html'}
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def iter_content(self, size): yield self.data


def test_robots_disallow_is_respected_before_article_request(monkeypatch):
    client = PublicClient(SOURCES['tourism'])
    called = []
    def get(url, **kwargs):
        called.append(url)
        return Response(data=b'User-agent: *\nDisallow: /news')
    monkeypatch.setattr(client.session, 'get', get)
    client.prepare()
    with pytest.raises(CollectionError, match='robots_denied'):
        client.html(TOURISM_URL)
    assert called == ['https://kankou-nabari.jp/robots.txt']


def test_absent_robots_is_allowed_but_server_error_fails_closed(monkeypatch):
    client = PublicClient(SOURCES['city'])
    monkeypatch.setattr(client.session, 'get', lambda *a, **k: Response(status=404))
    client.prepare()
    assert client.robots.can_fetch('NabariResearchCollector', CITY_URL)
    other = PublicClient(SOURCES['city'])
    monkeypatch.setattr(other.session, 'get', lambda *a, **k: Response(status=500))
    with pytest.raises(CollectionError, match='http_500'):
        other.prepare()


def test_external_redirect_is_never_followed(monkeypatch):
    client = PublicClient(SOURCES['city'])
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return Response(status=302, headers={'Location': 'https://127.0.0.1/private'})
    monkeypatch.setattr(client.session, 'get', get)
    with pytest.raises(ValueError):
        client._request(CITY_URL)
    assert calls == [CITY_URL]


def test_non_html_and_oversized_pages_are_rejected(monkeypatch):
    client = PublicClient(SOURCES['city'])
    monkeypatch.setattr(client.session, 'get', lambda *a, **k: Response(headers={'Content-Type': 'application/pdf'}))
    with pytest.raises(CollectionError, match='not_html'):
        client._request(CITY_URL)
    client.last_request = 0
    monkeypatch.setattr(client.session, 'get', lambda *a, **k: Response(headers={'Content-Type': 'text/html', 'Content-Length': '99999999'}))
    with pytest.raises(CollectionError, match='page_too_large'):
        client._request(CITY_URL)
