import csv
import logging
import logging.config
import os
import time
from contextlib import contextmanager

from datetime_sheet import EPOCH, datetime
import gspread
from fs import open_fs
import google.auth
import dpath.util as dpath
import yaml
import geddit

logging.config.fileConfig(os.path.join(os.path.dirname(__file__), 'logging.conf'))

LOGGER = logging.getLogger(__name__)

SPREADSHEETS_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]

# the name of the worksheet maintaining processed files
WORKSHEET_PROCESSED = 'Processed'

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


def load_conversions():
    """
    Loads configuration for how to map/convert CSV rows to sheet rows from multiple urls. A map of
    created converters are return: an array (one per sheet row) for each account name.
    """
    conversions = {}
    for url in os.environ['CONVERSIONS_URLS'].split():
        LOGGER.info(f'Loading conversions from {url}')
        conversions = dpath.merge(conversions, yaml.safe_load(geddit.geddit(url)))

    conversions_module = __import__('conversions')

    return {
        file_type: [
            # dynamically call create converter functions in the conversions module
            getattr(conversions_module, f"create_{creator}")(
                *args, conversions=conversions
            )
            for creator, *args in conversion
        ]
        for file_type, conversion in conversions['conversions'].items()
    }


def get_or_create_processed(spreadsheet):
    """Gets or creates the 'Processed' worksheet. If creating, writes the header row"""
    try:
        processed = spreadsheet.worksheet(WORKSHEET_PROCESSED)
    except gspread.WorksheetNotFound:
        processed = spreadsheet.add_worksheet(title=WORKSHEET_PROCESSED, rows=1, cols=1)
        processed.update_cell(1, 1, 'Files Processed')
    return processed


def get_or_create_transactions(spreadsheet, worksheet_name):
    """Gets or creates a transactions worksheet. If creating, writes the header row"""
    try:
        transactions = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        transactions = spreadsheet.add_worksheet(
            title=worksheet_name, rows=1, cols=len(COLUMNS)
        )
        cell_list = transactions.range(1, 1, 1, len(COLUMNS))
        for i, column in enumerate(COLUMNS):
            cell_list[i].value = column
        transactions.update_cells(cell_list)
        # if we format the date header row with the required date format,
        # subsequent values will use this format.
        transactions.format(gspread.utils.rowcol_to_a1(1, DATE + 1), {
            "numberFormat": {
                "type": "DATE",
                "pattern": "yyyy-mm-dd"
            }
        })
    return transactions


def get_worksheet_name(sheet_date):
    """
    Generates the transaction worksheet's name from a sheet date (epoch date).
    Each transaction worksheets arec divided into tax years.
    """
    date = EPOCH + datetime.timedelta(days=sheet_date)
    year = date.year
    if date < datetime.datetime(year, 4, 1, 0, 0):
        year -= 1
    return f'Transactions {year}/{year + 1}'


@contextmanager
def append_new_rows(sheet, new_rows, columns):
    """
    A context manager to simplify the creation of new rows
    """
    # add new rows and retrieve the new blank rows
    sheet.add_rows(new_rows)
    new_cells = sheet.range(sheet.row_count + 1, 1, sheet.row_count + new_rows, columns)

    # yield to populate the new rows
    yield new_cells

    # update the new rows
    sheet.update_cells(new_cells)


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

    One or more conversion configuration files must be provided and between them they define how
    the CSV files in each of the account folders should be mapped/converted to the sheet.
    """
    conversions = load_conversions()

    credentials, _ = google.auth.default(scopes=SPREADSHEETS_SCOPE)

    gc = gspread.authorize(credentials)

    spreadsheet = gc.open_by_key(os.environ['SPREADSHEET_KEY'])

    # the 'Processed' worksheet
    processed = get_or_create_processed(spreadsheet)

    # A list of processed files retrieved from the 'Processed' worksheet
    existing_files = {file for file in processed.col_values(
        1, value_render_option='FORMULA'
    )}

    # A list of new files processed
    new_files = []

    # open the input path
    input_path = open_fs(os.environ['INPUT_PATH'])

    # the date before which transactions should be ignored
    cut_off_date = os.environ.get('CUT_OFF_DATE', 0)

    # a `dict` (keyed on worksheet) of sets of existing ids
    existing_ids_by_worksheet = {}

    # a `dict` (keyed on worksheet) of lists of converted sheet rows returned from
    # `process_download()`
    new_rows_by_worksheet = {}

    def validate_and_assign_row(sheet_row):
        """
        Validate a row and assign it to a transaction worksheet (if it isn't already in there).
        If the row is valid and not a duplicate then the worksheet name is returned
        (else None). `existing_ids_by_worksheet` is also populated here, if required.
        """
        # is the transaction non-zero and after the `cut_off_date`?
        valid_so_far = (
            not (sheet_row[MONEY_IN] is None and sheet_row[MONEY_OUT] is None) and
            sheet_row[DATE] >= cut_off_date
        )

        # if the transaction is valid check that it isn't already in the worksheet
        # (populating `existing_ids_by_worksheet`, if required) and assign the transaction
        if valid_so_far:
            worksheet_name = get_worksheet_name(sheet_row[DATE])
            if worksheet_name not in existing_ids_by_worksheet:
                transactions = get_or_create_transactions(spreadsheet, worksheet_name)
                # retrieve all the existing ids from the sheet
                existing_ids_by_worksheet[worksheet_name] = {
                    id for id in transactions.col_values(ID + 1, value_render_option='FORMULA')
                }
                # also initialise `new_rows_by_worksheet`
                new_rows_by_worksheet[worksheet_name] = []

            if sheet_row[ID] not in existing_ids_by_worksheet[worksheet_name]:
                new_rows_by_worksheet[worksheet_name].append(sheet_row)
                # add the new id to the existing ids
                existing_ids_by_worksheet[worksheet_name].add(sheet_row[ID])

    def process_download(file_type, account_name, file_name):
        """
        A closure that processes a CSV `file_name` for a particular `file_type` and `account_name`
        and updates list of new rows and set of existing ids.
        """

        # get the row converters
        converters = [lambda _: account_name] + conversions[file_type]
        with input_path.open(file_name) as csvfile:
            reader = csv.reader(csvfile)
            # discard the header
            next(reader)
            # convert a row, validate it, and assign it to a worksheet to be added at the end.
            for row in reader:
                validate_and_assign_row([convert(row) for convert in converters])

    # walk the tree of CSV files
    for step in input_path.walk(filter=['*.csv']):
        path = step.path.split('/')
        for file in step.files:
            file_name = f'{step.path}/{file.name}'
            # process the file if it doesn't exists in 'Processed'
            if file_name not in existing_files:
                LOGGER.info(f'Processing {file_name}')
                file_type = path[1]
                account_name = path[2]
                process_download(file_type, account_name, file_name)
                # add the file_name to new_files
                new_files.append(file_name)

    total_transactions = 0

    # for each worksheet..
    for worksheet_name, new_rows in new_rows_by_worksheet.items():
        total_transactions += len(new_rows)
        if len(new_rows) > 0:
            LOGGER.info(f'{worksheet_name}: {len(new_rows)} new transactions')

            transactions = get_or_create_transactions(spreadsheet, worksheet_name)

            current_row_count = transactions.row_count

            # append new rows to transaction sheet
            with append_new_rows(transactions, len(new_rows), len(COLUMNS)) as new_row_cells:
                for i, row in enumerate(new_rows):
                    for j, value in enumerate(row):
                        new_row_cells[i * len(COLUMNS) + j].value = value

            # always re-sort the transactions after 1 second
            time.sleep(1)
            end = gspread.utils.rowcol_to_a1(current_row_count + len(new_rows), len(COLUMNS))
            transactions.sort((2, 'asc'), range=f'A2:{end}')

    LOGGER.info(f'Total: {total_transactions} new transactions')

    if len(new_files) > 0:
        # append new files to processed sheet
        with append_new_rows(processed, len(new_files), 1) as new_file_cells:
            for i, value in enumerate(new_files):
                new_file_cells[i].value = value


if __name__ == "__main__":
    main()
