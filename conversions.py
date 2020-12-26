"""
This module defines converters that can be used in the conversions configuration to convert bank
specific CSV fields to a spreadsheet fields. For example, the configuration
`["convert_date", 0, "%Y-%m-%d"]` will call `create_convert_date(0, "%Y-%m-%d")` which returns a
convert function accepting a `row` parameter.
"""
import hashlib
from datetime_sheet import EPOCH, datetime


def create_identity(index, **kwargs):
    """
    returns a converter that performs no convertion on field `index`
    """
    return lambda row: row[index]


def create_constant(constant, **kwargs):
    """
    returns a converter that always returns `constant`
    """
    return lambda _: constant


def create_convert_date(index, format, **kwargs):
    """
    returns a converter for field `index` that converts the value (of format `format`) to a sheet
    date
    """
    return lambda row: (datetime.datetime.strptime(row[index], format) - EPOCH).days


def create_convert_amount_simple(index, **kwargs):
    """
    returns a converter for field `index` that converts the value to an amount
    """
    return lambda row: abs(float(row[index])) if row[index] else None


def create_convert_amount(index, is_out, **kwargs):
    """
    returns a converter for field `index` that converts the value to either an 'in' or 'out amount
    """
    def convert_amount(row):
        amount = float(row[index])
        amount = abs(min(amount, 0) if is_out else max(amount, 0))
        return amount if amount > 0 else None
    return convert_amount


def create_generate_id(indices, **kwargs):
    """
    Returns a converter for fields `indices` that converts then to a hash to be used as an id.
    NOTE: this isn't guaranteed to produce a unique ID also any updates to the transaction data
    will cause to id to change.
    """
    def convert_id(row):
        sha256 = hashlib.sha256()
        for i in indices:
            sha256.update(row[i].encode('utf-8'))
        return sha256.hexdigest()[:16]
    return convert_id


def create_convert_category(notes_index, category_index, category_map_name, config):
    """
    Returns a converter for a spending category. Attempts to resolve a valid category from either a
    tag in the "notes" row or then the "category" row. Valid categories are defined in
    `config['categories']` and additional category mappings and tag mappings are defined in
    `config[category_map_name]`. The tags aren't case sensitive.
    """
    # make a "set like" dict of all the categories
    category_map = {category: category for category in config['categories']}
    # update it with all the extra category and tag mappings
    category_map.update(config[category_map_name])

    def convert_category(row):
        categories = [word.lower() for word in row[notes_index].split() if word.startswith('#')]
        categories.append(row[category_index])
        for category in categories:
            if category in category_map:
                return category_map[category]
        return None
    return convert_category
