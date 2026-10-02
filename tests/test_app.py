import pytest

import main

DEMOS = ['sample_sales_enhanced', 'synthetic_sales_100', 'supermarket_data']
DASHBOARDS = ['executive', 'financial', 'growth', 'trends', 'inventory', 'chat']


@pytest.fixture
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        yield c


def test_pages_need_login():
    with main.app.test_client() as c:
        r = c.get('/dashboard/executive')
        assert r.status_code == 302
        assert '/login' in r.headers['Location']


@pytest.mark.parametrize('demo', DEMOS)
def test_every_dashboard_renders_for_every_demo(client, demo):
    r = client.post('/load-demo-data', data={'demo_type': demo, 'date_filter': 'all'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/dashboard/executive')
    for name in DASHBOARDS:
        page = client.get(f'/dashboard/{name}')
        assert page.status_code == 200, f'{name} dashboard failed for {demo}'


@pytest.mark.parametrize('demo', DEMOS)
def test_totals_add_up(demo):
    insights, error = main.analyze_sales_data(f'{demo}.csv')
    assert error is None
    assert insights['total_profit'] == pytest.approx(insights['total_sales'] - insights['total_cost'])
    monthly = insights['monthly_trends']
    assert sum(m['Revenue'] for m in monthly) == pytest.approx(insights['total_sales'])


def test_missing_columns_are_reported(tmp_path):
    bad = tmp_path / 'bad.csv'
    bad.write_text('Date,Product_Name,Quantity\n2024-01-01,Tea,2\n')
    insights, error = main.analyze_sales_data(str(bad))
    assert insights is None
    assert 'Missing required columns' in error


@pytest.mark.parametrize('target,expected', [
    ('/dashboard/financial', '/dashboard/financial'),
    ('https://evil.example/phish', '/home'),
    ('//evil.example/phish', '/home'),
    ('/\\evil.example', '/home'),
])
def test_login_only_redirects_within_the_app(target, expected):
    with main.app.test_client() as c:
        r = c.post('/login?next=' + target, data={'username': 'demo', 'password': 'demo'})
        assert r.headers['Location'] == expected


def test_money_filter_adds_thousands_separators():
    assert main.money(76369.4) == '76,369'
    assert main.money(1234.5, 2) == '1,234.50'
    assert main.money('n/a') == 'n/a'


def _page(client, name, demo='supermarket_data'):
    client.post('/load-demo-data', data={'demo_type': demo, 'date_filter': 'all'})
    return client.get(f'/dashboard/{name}').get_data(as_text=True)


def test_financial_page_ranks_products_and_collapses_brands(client):
    page = _page(client, 'financial')
    table = page.split('Top 10 Products by Revenue')[1].split('</table>')[0]
    assert table.index('Chicken Breast') < table.index('Beef Mince')
    assert 'Apples' not in table  # $897 of revenue: alphabetical order used to put it first
    assert 'Show the other 56 brands' in page


def test_growth_page_shows_real_average_order_value(client):
    page = _page(client, 'growth')
    assert 'Average Order Value' in page and '$17.04' in page


def test_chat_overview_counts_products(client):
    page = _page(client, 'chat')
    assert '>30<' in page.replace(' ', '').replace('\n', '')
