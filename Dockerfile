FROM python:3.9-slim
COPY . /usr/src/app
WORKDIR /usr/src/app
RUN ["pip", "install", "-r", "requirements.txt"]
ENTRYPOINT ["python", "main.py"]
