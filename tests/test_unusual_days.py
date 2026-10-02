import numpy as np
import pandas as pd

import main
from analytics import detect_unusual_days


def frame(revenues, start='2024-01-01', product='Tea', spike_product=None, spike_day=None):
    rows = []
    for i, r in enumerate(revenues):
        day = pd.Timestamp(start) + pd.Timedelta(days=i)
        name = spike_product if spike_product and i == spike_day else product
        rows.append({'Date': day, 'Product': name, 'Revenue': float(r)})
    return pd.DataFrame(rows)


def steady(n, seed=0):
    rng = np.random.default_rng(seed)
    return 100 + rng.normal(0, 5, n)


def test_a_single_spike_is_found_with_its_driver():
    values = steady(60)
    values[30] = 400
    result = detect_unusual_days(frame(values, spike_product='Wedding Cake', spike_day=30))
    assert result['available']
    assert [d['date'] for d in result['days']] == ['2024-01-31']
    day = result['days'][0]
    assert day['direction'] == 'spike' and day['top_product'] == 'Wedding Cake'
    assert day['change_pct'] > 200


def test_a_dip_is_found_too():
    values = steady(60, seed=1)
    values[40] = 5
    result = detect_unusual_days(frame(values))
    assert [d['direction'] for d in result['days']] == ['dip']


def test_ordinary_noise_raises_no_flags():
    assert detect_unusual_days(frame(steady(90, seed=2)))['days'] == []


def test_closed_days_are_not_counted_as_crashes():
    values = steady(70, seed=3)
    df = frame(values)
    open_days = df[df['Date'].dt.dayofweek != 6]  # closed every Sunday
    assert detect_unusual_days(open_days)['days'] == []


def test_short_history_explains_itself():
    result = detect_unusual_days(frame(steady(10)))
    assert not result['available'] and '30' in result['reason']


def test_financial_dashboard_lists_unusual_days():
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        c.post('/load-demo-data', data={'demo_type': 'supermarket_data', 'date_filter': 'all'})
        page = c.get('/dashboard/financial').get_data(as_text=True)
    assert 'Unusual Days' in page and 'Beef Mince' in page


def test_false_alarm_rate_on_ordinary_noise_is_zero():
    flags = sum(len(detect_unusual_days(frame(steady(90, seed=s)))['days']) for s in range(100))
    assert flags == 0
