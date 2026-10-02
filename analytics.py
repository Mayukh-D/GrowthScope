"""Pure analytics helpers, kept out of main.py so they can be unit tested
without a Flask app or a session."""

import warnings

import numpy as np
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


# --- Revenue forecast -----------------------------------------------------

MIN_MONTHS_FOR_FORECAST = 6
SEASONAL_MONTHS = 24
# z for a central 80% interval. Ranges that wide are honest for small-shop
# data; a 95% band would mostly say "anything could happen".
Z80 = 1.2816


def _fit(values, months, seasonal):
    """Linear trend, optionally times a month-of-year index. Returns a
    predict(i, month_of_year) function."""
    x = np.arange(len(values), dtype=float)
    y = np.asarray(values, dtype=float)
    index = {m: 1.0 for m in range(1, 13)}
    if seasonal:
        slope, intercept = np.polyfit(x, y, 1)
        trend = np.maximum(slope * x + intercept, 1e-9)
        ratios = {}
        for m, actual, base in zip(months, y, trend):
            ratios.setdefault(m, []).append(actual / base)
        raw = {m: float(np.mean(r)) for m, r in ratios.items()}
        mean = float(np.mean(list(raw.values())))
        index.update({m: r / mean for m, r in raw.items()})
        y = y / np.array([index[m] for m in months])
    slope, intercept = np.polyfit(x, y, 1)
    return lambda i, m: max((slope * i + intercept) * index[m], 0.0)


def forecast_monthly_revenue(monthly_trends, data_end=None, horizon=3):
    """Project monthly revenue `horizon` months ahead.

    `monthly_trends` is the app's list of {'Month_str': 'YYYY-MM',
    'Revenue': ...}. A final month the data does not cover to its end is
    left out of the fit, so a file ending on the 10th does not read as a
    crash. Returns None, with a reason, when there is too little history.

    The result carries its own track record: the model is refitted without
    the last three known months and scored on them (mean absolute
    percentage error), so the dashboard can say how far off it has been.
    """
    if not monthly_trends:
        return {'available': False, 'reason': 'No monthly data.'}

    periods = [pd.Period(m['Month_str'], 'M') for m in monthly_trends]
    revenue = [float(m['Revenue']) for m in monthly_trends]
    order = np.argsort([p.ordinal for p in periods])
    periods = [periods[i] for i in order]
    revenue = [revenue[i] for i in order]

    excluded = None
    if data_end is not None:
        end = pd.Timestamp(data_end)
        last = periods[-1]
        if end.to_period('M') == last and end.day < last.days_in_month - 2:
            excluded = last.strftime('%b %Y')
            periods, revenue = periods[:-1], revenue[:-1]

    if len(revenue) < MIN_MONTHS_FOR_FORECAST:
        return {'available': False,
                'reason': f'Needs at least {MIN_MONTHS_FOR_FORECAST} complete months of data; this file has {len(revenue)}.'}

    months = [p.month for p in periods]
    seasonal = len(revenue) >= SEASONAL_MONTHS
    predict = _fit(revenue, months, seasonal)
    n = len(revenue)

    fitted = np.array([predict(i, m) for i, m in enumerate(months)])
    residual_sd = float(np.std(np.array(revenue) - fitted, ddof=1)) if n > 2 else 0.0

    points = []
    for h in range(1, horizon + 1):
        period = periods[-1] + h
        value = predict(n - 1 + h, period.month)
        spread = Z80 * residual_sd * np.sqrt(1 + h / n)
        points.append({
            'month': period.strftime('%Y-%m'),
            'label': period.strftime('%b %Y'),
            'revenue': round(float(value), 2),
            'low': round(float(max(value - spread, 0.0)), 2),
            'high': round(float(value + spread), 2),
        })

    backtest_error = None
    if n >= MIN_MONTHS_FOR_FORECAST + 3:
        held_predict = _fit(revenue[:-3], months[:-3], len(revenue) - 3 >= SEASONAL_MONTHS)
        errors = [abs(held_predict(n - 4 + h, months[n - 4 + h]) - revenue[n - 4 + h]) / revenue[n - 4 + h]
                  for h in range(1, 4) if revenue[n - 4 + h] > 0]
        if errors:
            backtest_error = round(float(np.mean(errors)) * 100, 1)

    # Above this, the track record says the line is closer to noise than
    # signal, and the dashboard says so instead of drawing it confidently.
    confidence = 'low' if backtest_error is None or backtest_error > 35 else 'high' if backtest_error <= 15 else 'medium'

    return {
        'available': True,
        'confidence': confidence,
        'method': 'Trend with seasonality' if seasonal else 'Linear trend',
        'months_used': n,
        'excluded_partial_month': excluded,
        'backtest_error_pct': backtest_error,
        'history': [{'label': p.strftime('%b %Y'), 'revenue': round(float(r), 2)}
                    for p, r in list(zip(periods, revenue))[-12:]],
        'points': points,
    }
