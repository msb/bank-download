
This is a containerised script that iterates ...

To run the script in it's simplest form, create a `bankdownload.env` file with the following
variables:

```
OUTPUT_PATH=osfs:///data
```

Then running the following docker command will output the script to the current working directory:

```bash
docker run --rm \
  --env-file gitlabdownload.env \
  --user $(id -u):$(id -g) --volume "$PWD:/data" \
  msb140610/gitlab-download:2
```

The script uses [PyFilesystem](https://github.com/pyfilesystem/pyfilesystem2) to write to the
output path so the script can be configured to write to any file system supported by PyFilesystem
which could be useful if you aren't running docker locally. The container has been configured with
the `fs.dropboxfs` and  `fs.onedrivefs` third party file systems and a 
[custom WIP version of `fs.googledrivefs`](https://github.com/msb/fs.googledrivefs/tree/file_id_support).

### Configuring the output path with fs.googledrivefs

There are different ways of authenticating to GDrive API but this example uses a service account
with permission on the target directory. The set up steps are sketched as follows:

 - create a GCP project
 - In that project:
   - create a GCP service account, downloading it's credentials file
   - enable the GDrive API
 - Allow the service account read/write permission on the target GDrive folder 
   (use it's email address)
 - Note the id of the target GDrive folder 

Then update the `gitlabdownload.env` file with the following variables:

```
OUTPUT_PATH=googledrive:///{the id of the target GDrive folder}?service_account_credentials_file=%2Fcredentials_file.json
```

Finally, run the container and the generated script with be written to the target GDrive folder
with no need for a bind volume.

```bash
docker run --rm --env-file gitlabdownload.env \
  --volume [path/to/credentials]:/credentials_file.json \
  msb140610/gitlab-download:2

```

This is quite a lot of effort for a fairly trivial script but it was a learning exercise and quite
helpful in understanding PyFilesystem and the GDrive API. 

It is also noted that the customisation of fs.googledrivefs is fairly hacky at the moment and I
hope to tidy it up in the future.

### Development

If you wish to make changes to the script then the source for the script and container
configuration can be cloned from [github](https://github.com/msb/gitlab-download). Once cloned the
script can be from the local project using a bind volume as follows:

```bash
docker run --rm \
  --env-file gitlabdownload.env \
  --volume "$PWD:/app" \
  msb140610/gitlab-download:2
```
Also the container has been configured with `ipython` if you wish to experiment with the gitlab
or PyFilesystem libraries as follows:

```bash
docker run --rm -it \
  --env-file gitlabdownload.env \
  --volume "$PWD:/app" \
  --entrypoint ipython \
  msb140610/gitlab-download:2
```

If the container configuration needs changing, it can be built for testing locally as follows:

```bash
docker build -t bank-download .
```

FIXME - need to enable https://console.developers.google.com/apis/library/sheets.googleapis.com?project=scratch-project-209811

docker run --rm --env-file bankdownload.env \
  --volume "$PWD:/app" \
  --volume $PWD/scratch-project-209811-70eb27d72bce.json:/credentials_file.json \
  bank-download

  --entrypoint /bin/sh -it \
