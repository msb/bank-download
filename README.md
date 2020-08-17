
This is a containerised script that walks a directory to find and upload CSV files containing bank
transactions to a Google spreadsheet. The script expects the following directory structure:
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

To run the script in it's simplest form, create a `bankdownload.env` file with the following
variables:

```
GOOGLE_APPLICATION_CREDENTIALS=/credentials.json
INPUT_PATH=osfs:///path/to/root
SPREADSHEET_KEY={sheet id}
```

To get the sheet id, create a sheet and then get the id from the sheet's. There are different ways
of authenticating to Google Sheets but this example uses a GCP service account with permission on the
target sheet. The set up steps are as follows:

 - Create [a GCP project](https://cloud.google.com/storage/docs/projects) to contain your cluster.
   [A Terraform module](https://github.com/msb/tf-gcp-project) has been provided to automate this 
   for you. Following the module's README you will see that this step has already been partially
   complete by the inclusion of 
   [the `project` folder](https://github.com/msb/bank-download/tree/master/project).
   Note that when running `terraform.output.sh` you should target the output at 
   [the `runner` folder](https://github.com/msb/bank-download/tree/master/runner).
 - Allow the service account read/write permission on the sheet 
   (use the email address found in the credentials file in the `runner` folder)

Then running the following docker command will output the script to the current working directory:

```bash
export VERSION=1.0

docker run --rm \
  --env-file bankdownload.env \
  --volume $PWD/runner/service_account_credentials.json:/credentials.json \
  --user $(id -u):$(id -g) --volume "$PWD:/data" \
  msb140610/bank-download:$VERSION
```

The script uses [PyFilesystem](https://github.com/pyfilesystem/pyfilesystem2) to write to the
output path so the script can be configured to write to any file system supported by PyFilesystem
which could be useful if you aren't running docker locally. The container has been configured with
the `fs.dropboxfs` and  `fs.onedrivefs` third party file systems and a 
[custom WIP version of `fs.googledrivefs`](https://github.com/msb/fs.googledrivefs/tree/service-account-support).

### Configuring the output path with fs.googledrivefs

The set up steps are sketched as follows:

 - Allow the service account read/write permission on the target GDrive folder
   (use the email address found in the credentials file in the `runner` folder)
 - Note the id of the target GDrive folder 

Then update the `bankdownload.env` file with the following variables:

```
INPUT_PATH=googledrive:///?root_id={the id of the target GDrive folder}
```

Finally, run the container and the generated script with be written to the target GDrive folder
with no need for a bind volume.

```bash
docker run --rm --env-file bankdownload.env \
  --volume $PWD/runner/service_account_credentials.json:/credentials.json \
  msb140610/bank-download:$VERSION
```

### Development

If you wish to make changes to the script then the source for the script and container
configuration can be cloned from [github](https://github.com/msb/bank-download). Once cloned the
container can be built for testing locally as follows:

```bash
docker build -t bank-download .
```

Changes to the script in the local project can be tested using a bind volume as follows:

```bash
docker run --rm \
  --env-file bankdownload.env \
  --volume $PWD/runner/service_account_credentials.json:/credentials.json \
  --volume "$PWD:/app" \
  bank-download
```

Also the container has been configured with `ipython` if you wish to experiment with the gitlab
or PyFilesystem libraries as follows:

```bash
docker run --rm -it \
  --env-file bankdownload.env \
  --volume $PWD/runner/service_account_credentials.json:/credentials.json \
  --volume "$PWD:/app" \
  --entrypoint ipython \
  bank-download
```
