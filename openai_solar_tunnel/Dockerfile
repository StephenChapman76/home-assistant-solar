ARG TUNNEL_CLIENT_IMAGE=ghcr.io/openai/tunnel-client:v0.0.13
FROM ${TUNNEL_CLIENT_IMAGE} AS tunnel_client

FROM ghcr.io/home-assistant/base:3.22

ARG BUILD_ARCH
ARG BUILD_VERSION

COPY --from=tunnel_client /usr/bin/tunnel-client /usr/local/bin/tunnel-client
COPY run.sh /

RUN chmod 0755 /run.sh /usr/local/bin/tunnel-client

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

CMD ["/run.sh"]
