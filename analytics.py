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
