import io

import pandas as pd
import pytest

import main


@pytest.fixture
def client():
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        yield c


def load(client, demo='supermarket_data', **form):
    client.post('/load-demo-data', data={'demo_type': demo, 'date_filter': 'all', **form})


def read(response):
    return pd.read_csv(io.StringIO(response.get_data(as_text=True)))


def test_monthly_report_matches_the_analysis_and_appends_the_forecast(client):
    load(client)
    r = client.get('/report/monthly.csv')
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    assert 'attachment; filename="growthscope-monthly-2023-01-02-to-2025-09-19.csv"' == r.headers['Content-Disposition']
    table = read(r)
    insights, _ = main.analyze_sales_data('supermarket_data.csv')
    actual = table[table['Type'] == 'Actual']
    assert actual['Revenue'].sum() == pytest.approx(insights['total_sales'], abs=1)
    assert (table['Type'] == 'Forecast').sum() == 3


def test_product_report_ranks_by_revenue_and_shares_sum_to_100(client):
    load(client)
    table = read(client.get('/report/products.csv'))
    assert list(table['Rank'][:3]) == [1, 2, 3]
    assert table['Revenue'].is_monotonic_decreasing
    assert table['Share of revenue %'].sum() == pytest.approx(100, abs=0.5)


def test_reports_respect_the_selected_date_range(client):
    load(client, date_filter='custom', start_date='2024-01-01', end_date='2024-03-31')
    table = read(client.get('/report/monthly.csv'))
    assert list(table[table['Type'] == 'Actual']['Month']) == ['2024-01', '2024-02', '2024-03']


def test_unknown_report_is_404_and_reports_need_data(client):
    assert client.get('/report/secrets.csv').status_code == 404
    r = client.get('/report/monthly.csv')
    assert r.status_code == 302


def test_reports_need_login():
    with main.app.test_client() as c:
        assert '/login' in c.get('/report/monthly.csv').headers['Location']
