FROM python

RUN git clone https://github.com/msb/fs.googledrivefs.git --branch service-account-support

WORKDIR /fs.googledrivefs

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python && \
    /root/.poetry/bin/poetry build

FROM python:3.8-alpine

ENV GOOGLEDRIVE_FS_DIST fs.googledrivefs-1.7.0-py3-none-any.whl

COPY --from=0 /fs.googledrivefs/dist/$GOOGLEDRIVE_FS_DIST /

WORKDIR /app

ADD ./ ./

RUN pip install --upgrade pip && \
    pip install /$GOOGLEDRIVE_FS_DIST && \
    pip install -r requirements.txt

VOLUME /app
VOLUME /data

ENTRYPOINT ["python3", "bankdownload.py"]