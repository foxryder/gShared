FROM ubuntu:latest
MAINTAINER Simon Waldner "voidnah@windhound.at"
RUN apt-get update -y && apt-get upgrade -y
RUN apt-get install -y ffmpeg python-pip python python-dev build-essential
COPY . /app
WORKDIR /app
RUN mkdir /downloads
RUN mkdir /logs
VOLUME /downloads
VOLUME /config
EXPOSE 5000
RUN pip install -r requirements.txt
RUN python setup.py install
ENTRYPOINT ["python"]
CMD ["app.py"]
