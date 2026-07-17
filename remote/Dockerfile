# syntax=docker/dockerfile:1.7

ARG KASM_ZOOM_IMAGE=kasmweb/zoom:1.18.0

FROM golang:1.22-alpine AS controller-builder

WORKDIR /src
COPY remote/go.mod remote/main.go ./
RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w" \
    -o /out/zoom-remote-controller ./main.go


FROM ${KASM_ZOOM_IMAGE} AS runtime

USER root

COPY --from=controller-builder --chmod=755 /out/zoom-remote-controller /usr/local/bin/zoom-remote-controller
COPY remote/custom_startup.sh /dockerstartup/custom_startup.remote.sh

RUN sed -i 's/\r$//' /dockerstartup/custom_startup.remote.sh \
    && chmod 755 /dockerstartup/custom_startup.remote.sh \
    && mv /dockerstartup/custom_startup.sh /dockerstartup/custom_startup.kasm.sh \
    && mv /dockerstartup/custom_startup.remote.sh /dockerstartup/custom_startup.sh \
    && mkdir -p /etc/opt/chrome/policies/managed \
    && echo '{"AutoLaunchProtocolsFromOrigins": [{"allowed_origins": ["*"], "protocol": "zoommtg"}, {"allowed_origins": ["*"], "protocol": "zoomus"}]}' > /etc/opt/chrome/policies/managed/zoom_policies.json \
    && mv /opt/zoom/ZoomWebviewHost /opt/zoom/ZoomWebviewHost.bin \
    && printf '#!/bin/bash\nexec /opt/zoom/ZoomWebviewHost.bin --no-sandbox "$@"\n' > /opt/zoom/ZoomWebviewHost \
    && chmod 755 /opt/zoom/ZoomWebviewHost

USER 1000
