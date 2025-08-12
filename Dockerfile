FROM alpine:3.22.1

LABEL app.nrtk-client-python.vendor="Digital Developments"
LABEL app.nrtk-client-python.version="0.1"
LABEL app.nrtk-client-python.release-date="2025-02-19"

RUN apk add --no-cache python3

WORKDIR /app

COPY ./main.py /app/main.py

ENTRYPOINT [ "python", "/app/main.py" ]
