import pandas as pd
import pytest

import main
from analytics import map_columns, normalise_sales_frame, to_number

SQUARE_STYLE = (
    'Transaction Date,Order ID,Item,Qty,Unit Price,Unit Cost\n'
    '15/01/2024,A1,Flat White,2,$5.50,$1.20\n'
    '16/01/2024,A2,Banana Bread,1,"$1,299.00",$300.00\n'
    '17/01/2024,A3,Muffin,two,$4.00,$1.00\n'
)


def test_common_header_variants_map_to_the_app_columns():
    mapping = map_columns(['Transaction Date', 'Order ID', 'Item', 'Qty', 'Unit Price', 'Unit Cost'])
    assert mapping == {
        'Transaction Date': 'Date', 'Order ID': 'Receipt_ID', 'Item': 'Product_Name',
        'Qty': 'Quantity', 'Unit Price': 'Selling_Price', 'Unit Cost': 'Cost_Price',
    }


def test_exact_header_wins_over_a_looser_synonym():
    mapping = map_columns(['Price', 'Selling_Price', 'Cost_Price'])
    assert mapping['Selling_Price'] == 'Selling_Price'
    assert 'Price' not in mapping


def test_currency_text_becomes_numbers():
    assert list(to_number(pd.Series(['$1,299.00', ' 4.50 ', '(12.00)', 'n/a']))[:3]) == [1299.0, 4.5, -12.0]
    assert pd.isna(to_number(pd.Series(['n/a']))[0])


def test_report_explains_what_happened():
    df = pd.read_csv(pd.io.common.StringIO(SQUARE_STYLE))
    clean, report, error = normalise_sales_frame(df)
    assert error is None
    assert report['filled'] == ['Brand_Name', 'Category']
    assert report['rows_dropped'] == 1 and report['rows_used'] == 2
    assert clean['Selling_Price'].tolist() == [5.5, 1299.0]


def test_a_real_world_export_analyses_end_to_end(tmp_path):
    path = tmp_path / 'square.csv'
    path.write_text(SQUARE_STYLE)
    insights, error = main.analyze_sales_data(str(path))
    assert error is None
    assert insights['total_sales'] == pytest.approx(2 * 5.5 + 1299.0)
    assert insights['data_report']['renamed']['Qty'] == 'Quantity'


def test_unrecognised_required_column_lists_accepted_names(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text('Date,Item,Qty,Amount\n2024-01-01,Tea,1,3\n')
    _, error = main.analyze_sales_data(str(path))
    assert 'Selling_Price' in error and 'unitprice' in error


def test_upload_shows_the_match_report_on_the_dashboard():
    import io
    main.app.config['TESTING'] = True
    with main.app.test_client() as c:
        c.post('/login', data={'username': 'demo', 'password': 'demo'})
        r = c.post('/home', data={'csv_file': (io.BytesIO(SQUARE_STYLE.encode()), 'square.csv'), 'date_filter': 'all'},
                   content_type='multipart/form-data')
        assert r.status_code == 302
        page = c.get('/dashboard/executive').get_data(as_text=True)
        assert 'Matched your columns' in page and '<strong>Qty</strong> → Quantity' in page
        assert '1 row skipped' in page
