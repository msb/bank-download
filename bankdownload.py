import os
import datetime
import logging
import logging.config
from fs import open_fs
from oauth2client.service_account import ServiceAccountCredentials
import gspread
import csv
import hashlib

logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.conf'))

LOGGER = logging.getLogger(__name__)

SPREADSHEETS_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]

# the name of the worksheet maintaining processed files
WORKSHEET_PROCESSED = 'Processed'

# the name of the transactions worksheet
WORKSHEET_TRANSACTIONS = 'Transactions'

# the Google Sheet's epoch date
EPOCH = datetime.datetime(1899, 12, 30)


def create_convert_date(index, format):
    """
    returns a converter for field `index` that converts the value (of format `format`) to a sheet
    date
    """
    return lambda row: (datetime.datetime.strptime(row[index], format) - EPOCH).days


def create_convert_amount_simple(index):
    """
    returns a converter for field `index` that converts the value to an amount
    """
    return lambda row: abs(float(row[index])) if row[index] else None


def create_convert_amount(index, out):
    """
    returns a converter for field `index` that converts the value to either an 'in' or 'out amount
    """
    def convert_amount(row):
        amount = float(row[index])
        amount = abs(min(amount, 0) if out else max(amount, 0))
        return amount if amount > 0 else None
    return convert_amount


def create_convert_id(indices):
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


# A map of matching category keyed by their category tags.
CATEGORIES = {f'#{category}': category for category in {
    'Transfer',
    'Maintenance',
    'Groceries',
    'Cash',
    'Holiday',
    'Auto',
    'Energy',
    'Presents',
    'Gadgets',
    'Pastimes',
    'Entertainment',
    'Mobile',
    'Internet',
    'Water',
    'Charity',
    'Medical',
    'Travel',
    'Betting',
    'Official',
    'Clothing',
    'Homeware',
    'Biking',
}}
CATEGORIES.update({
    '#CouncilTax': 'Council Tax',
    '#EatingOut': 'Eating Out',
    '#HomeInsurance': 'Home Insurance',
    '#WhiteGoods': 'White Goods',
    '#TVLicense': 'TV License',
})


def create_convert_monzo_category(notes_index, category_index):
    """
    Returns a converter for a monzo category. Uses the "category" row unless the "notes" row has a
    tag that matches a known category.
    """
    def convert_monzo_category(row):
        categories = [
            CATEGORIES[word] for word in row[notes_index].split()
            if word.startswith('#') and word in CATEGORIES
        ]

        for category in categories:
            return category

        return row[category_index]
    return convert_monzo_category


# the transactions worksheet's column titles
COLUMNS = [
    'Account', 'Date', 'Description', 'Type', 'Money In', 'Money Out', 'Id', 'Reconciled',
    'Category', 'Notes'
]

# the indices of key mapped columns
DATE = COLUMNS.index('Date')
MONEY_IN = COLUMNS.index('Money In')
MONEY_OUT = COLUMNS.index('Money Out')
ID = COLUMNS.index('Id')

# A list of converters for a Monzo CSV (version 1).
CONVERSION_MONZO = [
    create_convert_date(1, '%Y-%m-%dT%H:%M:%SZ'),
    lambda row: row[8],
    lambda row: row[6],
    create_convert_amount(2, False),
    create_convert_amount(2, True),
    lambda row: row[0],
    lambda _: 'x',
    create_convert_monzo_category(10, 6),
]

# A list of converters for a Monzo CSV (version 2).
CONVERSION_MONZO_2 = [
    create_convert_date(1, '%d/%m/%Y'),
    lambda row: row[4],
    lambda row: row[6],
    create_convert_amount(7, False),
    create_convert_amount(7, True),
    lambda row: row[0],
    lambda _: 'x',
    create_convert_monzo_category(11, 6),
]

# A list of converters for a Smile CSV.
CONVERSION_SMILE = [
    create_convert_date(0, '%Y-%m-%d'),
    lambda row: row[1],
    lambda row: row[2],
    create_convert_amount_simple(3),
    create_convert_amount_simple(4),
    create_convert_id(range(0, 5)),
]

# A list of converters for a Smile CC CSV.
CONVERSION_SMILE_CC = [
    create_convert_date(0, '%Y-%m-%d'),
    lambda row: row[1],
    lambda _: None,
    create_convert_amount_simple(2),
    create_convert_amount_simple(3),
    create_convert_id(range(0, 4)),
]

# A map of conversions keyed on the account name they apply to
CONVERSIONS = {
    ('Monzo', 'Monzo'): CONVERSION_MONZO,
    ('Monzo', 'Monzo Joint'): CONVERSION_MONZO,
    ('Monzo 2', 'Monzo'): CONVERSION_MONZO_2,
    ('Monzo 2', 'Monzo Joint'): CONVERSION_MONZO_2,
    ('Smile', 'Smile'): CONVERSION_SMILE,
    ('Smile', 'Smile Joint'): CONVERSION_SMILE,
    ('Smile CC', 'Smile CC'): CONVERSION_SMILE_CC,
    ('Smile CC', 'Smile CC Joint'): CONVERSION_SMILE_CC,
}


def get_or_create_processed(spreadsheet):
    """Gets or creates the 'Processed' worksheet. If creating, writes the header row"""
    try:
        processed = spreadsheet.worksheet(WORKSHEET_PROCESSED)
    except gspread.WorksheetNotFound:
        processed = spreadsheet.add_worksheet(title=WORKSHEET_PROCESSED, rows=1, cols=1)
        processed.update_cell(1, 1, 'Files Processed')
    return processed


def get_or_create_transactions(spreadsheet):
    """Gets or creates the 'Transactions' worksheet. If creating, writes the header row"""
    try:
        transactions = spreadsheet.worksheet(WORKSHEET_TRANSACTIONS)
    except gspread.WorksheetNotFound:
        transactions = spreadsheet.add_worksheet(
            title=WORKSHEET_TRANSACTIONS, rows=1, cols=len(COLUMNS)
        )
        cell_list = transactions.range(1, 1, 1, len(COLUMNS))
        for i, column in enumerate(COLUMNS):
            cell_list[i].value = column
        transactions.update_cells(cell_list)
    return transactions


def main():
    """
    This script walks a directory to find and upload CSV files containing bank transactions to a
    Google spreadsheet. The script expects the following directory structure:
        root
            {a CSV file format}
                {an account name}
                    {any name}.csv
                    {other name}.csv
                     :
                {other account name}
                    {any name}.csv
                    {other name}.csv
                     :
                 :
            {another CSV file format}
                {an account name}
                    {any name}.csv
                    {other name}.csv
                     :
                {other account name}
                    {any name}.csv
                    {other name}.csv
                     :
                 :
             :
    The names of the previously uploaded files are maintained in a worksheet called 'Processed' and
    not uploaded again. The script also checks that previously uploaded transactions are not
    uploaded again using the transaction's id. If the transaction doesn't have an id then one is
    generated. A cut-off date can be set before which no transactions are uploaded (useful when
    archiving transactions).
    """

    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        os.environ['SERVICE_ACCOUNT_CREDENTIALS_FILE'], SPREADSHEETS_SCOPE
    )

    gc = gspread.authorize(credentials)

    spreadsheet = gc.open_by_key(os.environ['SPREADSHEET_KEY'])

    # the 'Processed' worksheet
    processed = get_or_create_processed(spreadsheet)

    # the 'Transactions' worksheet
    transactions = get_or_create_transactions(spreadsheet)

    # open the input path
    input_path = open_fs(os.environ['INPUT_PATH'])

    # the date before which transactions should be ignored
    cut_off_date = os.environ.get('CUT_OFF_DATE', 0)

    # retrieve all the existing ids from the sheet
    existing_ids = {id for id in transactions.col_values(
        ID + 1, value_render_option='FORMULA'
    )}

    def process_download(file_type, account_name, file_name):
        """
        A closure that processes a CSV `file_name` for a particular `file_type` and `account_name`
        and returns a list of converted rows.
        """
        # get the id, money, and date converters for the file_type and account_name
        key = (file_type, account_name)
        convert_id = CONVERSIONS[key][ID - 1]
        convert_money_in = CONVERSIONS[key][MONEY_IN - 1]
        convert_money_out = CONVERSIONS[key][MONEY_OUT - 1]
        convert_date = CONVERSIONS[key][DATE - 1]
        # get the row converters
        converters = [lambda _: account_name] + CONVERSIONS[key]
        with input_path.open(file_name) as csvfile:
            reader = csv.reader(csvfile)
            # discard the header
            next(reader)
            # filter all the new non-zero transactions > the cut_off_date
            # and convert them to sheet rows
            rows = [
                [convert(row) for convert in converters]
                for row in reader if
                convert_id(row) not in existing_ids and
                convert_date(row) >= cut_off_date and
                not (convert_money_in(row) is None and convert_money_out(row) is None)
            ]
            return rows

    # a list of converted sheet rows returned from `process_download()`
    rows = []

    # walk the tree of CSV files
    for step in input_path.walk(filter=['*.csv']):
        path = step.path.split('/')
        for file in step.files:
            file_name = f'{step.path}/{file.name}'
            try:
                processed.find(file_name)
            except gspread.CellNotFound:
                # process the file if it doesn't exists in 'Processed'
                LOGGER.info(f'Processing {file_name}')
                file_type = path[1]
                account_name = path[2]
                rows += process_download(file_type, account_name, file_name)
                # add the file_name to processed
                processed.append_row([file_name], value_input_option='RAW')

    if len(rows) > 0:
        # add and retrieve the new blank rows
        transactions.add_rows(len(rows))
        cell_list = transactions.range(
            transactions.row_count + 1, 1, transactions.row_count + len(rows), len(COLUMNS)
        )
        # populate and update the new rows
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                cell_list[i * len(COLUMNS) + j].value = value
        transactions.update_cells(cell_list)


if __name__ == "__main__":
    main()
