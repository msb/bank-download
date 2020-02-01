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

WORKSHEET_PROCESSED = 'Processed'

WORKSHEET_TRANSACTIONS = 'Transactions'

COLUMNS = [
    'Account', 'Date', 'Description', 'Type', 'Amount', 'Id', 'Reconciled', 'Category', 'Notes'
]

ID_INDEX = COLUMNS.index('Id')

EPOCH = datetime.datetime(1899, 12, 30)


def create_convert_value(value):
    def convert_value(_):
        return value
    return convert_value


def create_convert_identity(index):
    def convert_identity(row):
        return row[index]
    return convert_identity


def create_convert_date(index, format):
    def convert_date(row):
        return (datetime.datetime.strptime(row[index], format) - EPOCH).days
    return convert_date


def create_convert_amount(index):
    def convert_amount(row):
        return float(row[index])
    return convert_amount


def create_convert_amounts(index_in, index_out):
    def convert_amounts(row):
        if row[index_in]:
            return float(row[index_in])
        return - float(row[index_out])
    return convert_amounts


def monzo_convert_id(row):
    return row[0]


def smile_convert_id(row):
    # FIXME make id smaller
    # NOTE this isn't guaranteed to produce a unique ID
    m = hashlib.sha256()
    for i in range(0, 5):
        m.update(row[i].encode('utf-8'))
    return m.hexdigest()


def smile_cc_convert_id(row):
    # NOTE this isn't guaranteed to produce a unique ID
    m = hashlib.sha256()
    for i in range(0, 4):
        m.update(row[i].encode('utf-8'))
    return m.hexdigest()


CONVERSION_MONZO = [
    (5, monzo_convert_id),
    (4, create_convert_amount(2)),
    (1, create_convert_date(1, '%Y-%m-%dT%H:%M:%SZ')),
    (2, create_convert_identity(8)),
    (3, create_convert_identity(6)),
    (6, create_convert_value('x')),
]

CONVERSION_SMILE = [
        (5, smile_convert_id),
        (4, create_convert_amounts(3, 4)),
        (1, create_convert_date(0, '%Y-%m-%d')),
        (2, create_convert_identity(1)),
        (3, create_convert_identity(2)),
]

CONVERSION_SMILE_CC = [
        (5, smile_cc_convert_id),
        (4, create_convert_amounts(2, 3)),
        (1, create_convert_date(0, '%Y-%m-%d')),
        (2, create_convert_identity(1)),
]

CONVERSIONS = {
    'Monzo': CONVERSION_MONZO,
    'Monzo Joint': CONVERSION_MONZO,
    'Smile': CONVERSION_SMILE,
    'Smile Joint': CONVERSION_SMILE,
    'Smile CC': CONVERSION_SMILE_CC,
    'Smile CC Joint': CONVERSION_SMILE_CC,
}

CONVERT_IDS = {
    account_name: conversions[0][1] for account_name, conversions in CONVERSIONS.items()
}

CONVERT_AMOUNTS = {
    account_name: conversions[1][1] for account_name, conversions in CONVERSIONS.items()
}

CONVERT_DATES = {
    account_name: conversions[2][1] for account_name, conversions in CONVERSIONS.items()
}


def create_converters(account_name):
    converters = [None] * len(COLUMNS)
    converters[0] = create_convert_value(account_name)
    for conversion in CONVERSIONS[account_name]:
        converters[conversion[0]] = conversion[1]
    return converters


def main():
    """
    This script ..
    """
    credentials = ServiceAccountCredentials.from_json_keyfile_name(
        os.environ['SERVICE_ACCOUNT_CREDENTIALS_FILE'], SPREADSHEETS_SCOPE
    )

    gc = gspread.authorize(credentials)

    spreadsheet = gc.open_by_key(os.environ['SPREADSHEET_KEY'])

    try:
        processed = spreadsheet.worksheet(WORKSHEET_PROCESSED)
    except gspread.WorksheetNotFound:
        processed = spreadsheet.add_worksheet(title=WORKSHEET_PROCESSED, rows=1, cols=1)
        processed.update_cell(1, 1, 'Files Processed')

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

    home_fs = open_fs(os.environ['INPUT_PATH'])

    def process_download(account_name, file, row_count):
        file_name = f'{step.path}/{file.name}'
        LOGGER.info(f'Processing {file_name}')
        try:
            processed.find(file_name)
        except gspread.CellNotFound:
            convert_id = CONVERT_IDS[account_name]
            convert_amount = CONVERT_AMOUNTS[account_name]
            existing = {id for id in transactions.col_values(
                ID_INDEX + 1, value_render_option='FORMULA'
            )}
            with home_fs.open(file_name) as csvfile:
                reader = csv.reader(csvfile)
                next(reader)  # headers not required
                converters = create_converters(account_name)
                rows = [
                    row for row in reader
                    if convert_id(row) not in existing and convert_amount(row) != 0
                ]
                if len(rows) > 0:
                    transactions.add_rows(len(rows))
                    cell_list = transactions.range(
                        row_count + 1, 1,
                        row_count + len(rows), len(COLUMNS)
                    )
                    for i, row in enumerate(rows):
                        for j, convert in enumerate(converters):
                            if convert:
                                cell_list[i * len(COLUMNS) + j].value = convert(row)
                    transactions.update_cells(cell_list)
                    row_count += len(rows)
            # FIXME processed.append_row([file_name], value_input_option='RAW')
        return row_count

    # row_count doesn't appear to update so we maintain it locally
    row_count = transactions.row_count

    for step in home_fs.walk(filter=['*.csv']):
        account_name = step.path[1:]
        for file in step.files:
            if account_name in ('Monzo', 'Smile Joint'):  # FIXME
                row_count = process_download(account_name, file, row_count)


if __name__ == "__main__":
    main()
