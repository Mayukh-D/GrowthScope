import pandas as pd
import pytest

import main
from analytics import forecast_monthly_revenue


def months(values, start='2023-01'):
    first = pd.Period(start, 'M')
    return [{'Month_str': str(first + i), 'Revenue': v} for i, v in enumerate(values)]


def test_a_clean_trend_is_projected_and_scores_itself_well():
    f = forecast_monthly_revenue(months([1000 + 100 * i for i in range(12)]))
    assert f['available'] and f['method'] == 'Linear trend'
    assert [p['revenue'] for p in f['points']] == pytest.approx([2200, 2300, 2400], abs=1)
    assert f['backtest_error_pct'] == pytest.approx(0, abs=0.1)
    assert f['confidence'] == 'high'


def test_seasonality_is_used_with_two_years_of_history():
    pattern = [1.0, 0.8, 0.9, 1.0, 1.1, 1.0, 0.9, 1.0, 1.1, 1.2, 1.4, 1.8]
    f = forecast_monthly_revenue(months([1000 * pattern[i % 12] for i in range(24)]))
    assert f['method'] == 'Trend with seasonality'
    # January after a December peak: the forecast should drop back.
    assert f['points'][0]['revenue'] < 0.7 * 1800


def test_a_partial_last_month_is_left_out():
    data = months([1000] * 8 + [200])  # the last month only has a week of sales
    f = forecast_monthly_revenue(data, data_end='2023-09-07')
    assert f['excluded_partial_month'] == 'Sep 2023'
    assert f['months_used'] == 8
    assert f['points'][0]['label'] == 'Sep 2023'


def test_too_little_history_says_why():
    f = forecast_monthly_revenue(months([100, 120, 130]))
    assert not f['available'] and '6' in f['reason']


def test_ranges_contain_the_forecast_and_never_go_negative():
    f = forecast_monthly_revenue(months([50, 400, 20, 600, 10, 300, 90, 20]))
    for p in f['points']:
        assert 0 <= p['low'] <= p['revenue'] <= p['high']
    assert f['confidence'] == 'low'


def test_dashboard_shows_the_forecast_for_the_supermarket_demo():
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        c.post('/load-demo-data', data={'demo_type': 'supermarket_data', 'date_filter': 'all'})
        page = c.get('/dashboard/executive').get_data(as_text=True)
    assert 'Revenue forecast, next 3 months' in page and 'forecastChart' in page
    assert 'Sep 2025 was left out' in page
