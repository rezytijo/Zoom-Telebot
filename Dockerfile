FROM python:3.13-rc-slim

WORKDIR /usr/src/app
COPY . .
RUN apt-get update && \
    apt-get install -y locales && \
    sed -i -e 's/# id_ID.UTF-8 UTF-8/id_ID.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

# RUN apt-get install -y python3 python3-pip

ENV LANG id_ID.UTF-8
ENV LC_ALL id_ID.UTF-8

RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD [ "python3", "./telegram_bot.py" ]
