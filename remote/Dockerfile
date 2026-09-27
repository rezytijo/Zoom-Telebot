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
    && echo '{"AutoLaunchProtocolsFromOrigins": [{"allowed_origins": ["*"], "protocol": "zoommtg"}, {"allowed_origins": ["*"], "protocol": "zoomus"}]}' > /etc/opt/chrome/policies/managed/zoom_policies.json

# NOTE: /opt/zoom/ZoomWebviewHost is left as the ELF binary the image ships.
# Wrapping it in a bash script to inject --no-sandbox made the client log
# "ZoomWebviewHost finally lanuch state is false" and leave the join dialog
# unpainted. The container runs unprivileged, so the real binary is correct.

USER 1000
