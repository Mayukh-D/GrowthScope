import pandas as pd

import main


def make(stock, monthly_units, months=3):
    rows = []
    for m in range(months):
        for day in range(monthly_units):
            rows.append({'Date': pd.Timestamp('2024-01-01') + pd.DateOffset(months=m) + pd.Timedelta(days=day % 28),
                         'Product': 'Tea', 'Quantity': 1, 'Stock_For_Month': stock,
                         'Cost_Price': 1.0, 'Selling_Price': 2.0})
    return pd.DataFrame(rows)


def test_days_of_cover_comes_from_the_rate_of_sale():
    inv = main.analyze_inventory_data(make(stock=60, monthly_units=30))
    tea = inv['products'][0]
    assert tea['days_of_cover'] == 60          # 60 units at one a day
    assert tea['days_until_restock'] == 53     # a week before running out


def test_reorder_dates_count_from_the_data_not_today():
    df = make(stock=10, monthly_units=30)
    inv = main.analyze_inventory_data(df)
    assert inv['as_of'] == df['Date'].max().strftime('%Y-%m-%d')
    assert inv['products'][0]['next_restock_date'] == (df['Date'].max().normalize() + pd.Timedelta(days=3)).strftime('%Y-%m-%d')


def test_nearly_out_means_reorder_now():
    inv = main.analyze_inventory_data(make(stock=3, monthly_units=30))
    assert inv['products'][0]['days_until_restock'] == 0
    assert inv['products'][0]['stock_level'] == 'Critical'
