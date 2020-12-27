
This is a containerised script that walks an input directory to find and upload CSV files
containing bank transactions to a Google spreadsheet. The script expects the following directory
structure:
```
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
```
The names of the previously uploaded files are maintained in a worksheet called 'Processed' and
not uploaded again. The script also checks that previously uploaded transactions are not
uploaded again using the transaction's id. If the transaction doesn't have an id then one is
generated. A cut-off date can be set before which no transactions are uploaded (useful when
archiving transactions).

One or more conversion configuration files must be provided and between them they define how
the CSV files in each of the account folders should be mapped/converted to the sheet.

To run the script in it's simplest form, create a `config.yml` using
[conversions.example.yml](https://github.com/msb/bank-download/blob/master/conversions.example.yml)
as a reference and place the resulting file in
[the `runner` folder](https://github.com/msb/bank-download/tree/master/runner).

You will need to set a sheet id in the config. To get it, create a sheet and then get the id from
the sheet's URL. There are different ways of authenticating to Google Sheets but this example uses
a GCP service account with permission on the target sheet. The set up steps are as follows:

 - Create [a GCP project](https://cloud.google.com/storage/docs/projects) to contain your cluster.
   [A Terraform module](https://github.com/msb/tf-gcp-project) has been provided to automate this 
   for you. Following the module's README you will see that this step has already been partially
   complete by the inclusion of 
   [the `project` folder](https://github.com/msb/bank-download/tree/master/project).
   Note that when running `terraform.output.sh` you should target the output at 
   [the `runner` folder](https://github.com/msb/bank-download/tree/master/runner) as the following
   documentation expects to find the service account credentials there.
 - Allow the service account read/write permission on the sheet 
   (use the email address found in the credentials file in the `runner` folder)

Then running the following docker command will input the data from the current working directory
(A [docker-compose.yml](https://github.com/msb/bank-download/blob/master/docker-compose.yml) file
is included to simplify running the container):

```bash
docker-compose run --rm --volume "$PWD:/data" bank-download
```

The script uses [PyFilesystem](https://github.com/pyfilesystem/pyfilesystem2) to write to the
output path so the script can be configured to write to any file system supported by PyFilesystem
which could be useful if you aren't running docker locally. The container has been configured with
the `fs.dropboxfs`, `fs.onedrivefs`, and `fs.googledrivefs` third party file systems.

### Configuring the output path with fs.googledrivefs

The set up steps are sketched as follows:

 - Allow the service account read/write permission on the target GDrive folder
   (use the email address found in the credentials file in the `runner` folder)
 - Note the id of the target GDrive folder 

Then update the `config.yml` file with:

```
input_path: googledrive:///?root_id={the id of the target GDrive folder}
```

Finally, run the container and the generated script with be written to the target GDrive folder
with no need for a bind volume.

```bash
docker-compose run --rm bank-download
```

### Development

If you wish to make changes to the script then the source for the script and container
configuration can be cloned from [github](https://github.com/msb/bank-download). Once cloned and
changes to the local project have been made, they can be tested using a bind volume as follows:

```bash
docker-compose run --rm bank-download-dev
```

Also the container has been configured with `ipython` if you wish to experiment with the gspread
or PyFilesystem libraries as follows:

```bash
docker-compose run -T --entrypoint ipython --rm bank-download-dev

# It seems the above command doesn't support special characters when editing (backspace, etc)
# so you could fall back to using docker:
docker build -t bank-download .
docker run --rm -it \
  -e "GOOGLE_APPLICATION_CREDENTIALS=/config/service_account_credentials.json" \
  -e "CONFIG_URLS=/config/config.yml" \
  --volume $PWD/runner:/config \
  --volume "$PWD:/app" \
  --entrypoint ipython \
  bank-download

```
