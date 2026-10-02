import pandas as pd

from analytics import parse_sales_dates
from main import analyze_sales_data


def test_day_first_dates_are_read_as_australian():
    parsed = parse_sales_dates(['02/01/2023', '25/12/2023'])
    assert list(parsed) == [pd.Timestamp('2023-01-02'), pd.Timestamp('2023-12-25')]


def test_iso_dates_are_unaffected():
    parsed = parse_sales_dates(['2023-03-16', '2023-11-02'])
    assert list(parsed) == [pd.Timestamp('2023-03-16'), pd.Timestamp('2023-11-02')]


def test_month_first_file_still_reads_when_unambiguous():
    # 12/25 cannot be day-first, so the month-first reading wins.
    parsed = parse_sales_dates(['12/25/2023', '01/31/2024'])
    assert list(parsed) == [pd.Timestamp('2023-12-25'), pd.Timestamp('2024-01-31')]


def test_supermarket_demo_keeps_every_row():
    rows = len(pd.read_csv('supermarket_data.csv'))
    insights, error = analyze_sales_data('supermarket_data.csv')
    assert error is None
    assert insights['raw_data'].shape[0] == rows
