"""Pure analytics helpers, kept out of main.py so they can be unit tested
without a Flask app or a session."""

import warnings

import pandas as pd


def parse_sales_dates(values):
    """Parse a column of dates, choosing day-first or month-first by which
    reads more of them.

    Australian exports write 02/01/2023 for 2 January. pandas defaults to
    month-first, which turns every day above 12 into a parse failure and
    puts the rest in the wrong month. ISO dates (2023-01-02) read the same
    either way, so they are unaffected. Ties go to day-first, since the app
    is built for Australian businesses.
    """
    values = pd.Series(values)
    # Both readings are tried on purpose, so pandas' "could not infer
    # format" and "dayfirst ignored for ISO" warnings are expected noise.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        month_first = pd.to_datetime(values, errors='coerce')
        day_first = pd.to_datetime(values, errors='coerce', dayfirst=True)
    if day_first.isna().sum() <= month_first.isna().sum():
        return day_first
    return month_first


# --- Column mapping -------------------------------------------------------

# Header variants seen in real exports (Square, Shopify, Excel), keyed by the
# canonical column the app uses. Headers are compared after lowercasing and
# dropping everything but letters and digits, so "Unit Price", "unit_price"
# and "UNIT-PRICE" all read as "unitprice".
COLUMN_SYNONYMS = {
    'Date': ['date', 'transactiondate', 'orderdate', 'saledate', 'solddate', 'day'],
    'Receipt_ID': ['receiptid', 'receipt', 'receiptno', 'receiptnumber', 'orderid', 'ordernumber',
                   'transactionid', 'invoice', 'invoiceid', 'invoiceno', 'invoicenumber'],
    'Product_Name': ['productname', 'product', 'item', 'itemname', 'productdescription', 'description'],
    'Brand_Name': ['brandname', 'brand', 'manufacturer', 'vendor', 'supplier'],
    'Category': ['category', 'productcategory', 'department', 'producttype', 'type'],
    'Quantity': ['quantity', 'qty', 'units', 'unitssold', 'quantitysold', 'count'],
    'Selling_Price': ['sellingprice', 'price', 'unitprice', 'saleprice', 'retailprice', 'priceperunit'],
    'Cost_Price': ['costprice', 'unitcost', 'costperunit', 'purchaseprice', 'cogs', 'cost'],
    'Stock_For_Month': ['stockformonth', 'stock', 'stocklevel', 'stockonhand', 'onhand', 'inventory'],
}

REQUIRED_COLUMNS = ['Date', 'Product_Name', 'Quantity', 'Selling_Price', 'Cost_Price']
OPTIONAL_DEFAULTS = {'Brand_Name': 'Unknown', 'Category': 'Uncategorised'}
NUMERIC_COLUMNS = ['Quantity', 'Selling_Price', 'Cost_Price', 'Stock_For_Month']


def _key(header):
    return ''.join(ch for ch in str(header).lower() if ch.isalnum())


def map_columns(columns):
    """Return {original header: canonical column} for the headers we
    recognise. A canonical column is claimed by the first header that
    matches it exactly, then by the earliest synonym, so an exact
    "Selling_Price" beats a looser "Price" in the same file."""
    keys = {col: _key(col) for col in columns}
    mapping = {}
    for canonical, synonyms in COLUMN_SYNONYMS.items():
        if canonical in columns:
            mapping[canonical] = canonical
            continue
        for synonym in synonyms:
            match = next((col for col, k in keys.items() if k == synonym and col not in mapping), None)
            if match is not None:
                mapping[match] = canonical
                break
    return mapping


def to_number(series):
    """Read numbers written as text: "$1,299.00", " 4.50 ", "(12.00)"."""
    text = series.astype(str).str.strip()
    negative = text.str.startswith('(') & text.str.endswith(')')
    cleaned = text.str.replace(r'[^0-9.\-]', '', regex=True)
    numbers = pd.to_numeric(cleaned, errors='coerce')
    return numbers.where(~negative, -numbers)


def normalise_sales_frame(df):
    """Rename recognised headers, fill optional columns, and clean numbers.

    Returns (frame, report, error). `report` says what was matched and how
    many rows were unusable, so the dashboard can tell the user rather than
    silently changing their totals. `error` is set when a required column
    cannot be found under any recognised name.
    """
    mapping = map_columns(list(df.columns))
    renamed = {orig: canon for orig, canon in mapping.items() if orig != canon}
    df = df.rename(columns=mapping)

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        accepted = '; '.join(f"{col} (e.g. {', '.join(COLUMN_SYNONYMS[col][:3])})" for col in missing)
        return None, None, f"Missing required columns: {', '.join(missing)}. Accepted names: {accepted}."

    filled = []
    for col, default in OPTIONAL_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
            filled.append(col)

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = to_number(df[col])

    before = len(df)
    df = df.dropna(subset=['Quantity', 'Selling_Price', 'Cost_Price'])
    report = {
        'renamed': renamed,
        'filled': filled,
        'rows_dropped': before - len(df),
        'rows_used': len(df),
    }
    return df, report, None
