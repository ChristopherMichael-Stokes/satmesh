# GDAL with the ECW driver, for converting EA vertical photography (ECW only) to GeoTIFF.
# No apt package or pip wheel carries the driver: the SDK is proprietary.
# libecwj2 3.3 is the SDK build GDAL's own ubuntu-full image uses; it reads ECW version 2 only,
# which every EA file checked is (2008 and 2020 surveys).
FROM ubuntu:24.04

ARG GDAL_VERSION=3.13.3
ARG GDAL_SHA256=5e0c388d83da2d686cc00a40272882432cdb54edff43d4af173e532844a0a0ea
ARG LIBECWJ2_SHA256=abe4f5d2dad2afdc2a9516e8794662b41dc62f4d791b1c039a222cd9bc4fac85

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential cmake curl ca-certificates libproj-dev proj-data libtiff-dev libgeotiff-dev \
      libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/build
RUN curl --retry 3 -fsSLO https://github.com/rouault/libecwj2-3.3-builds/releases/download/v1/install-libecwj2-3.3-ubuntu-20.04.tar.gz \
    && echo "${LIBECWJ2_SHA256}  install-libecwj2-3.3-ubuntu-20.04.tar.gz" | sha256sum -c - \
    && tar xzf install-libecwj2-3.3-ubuntu-20.04.tar.gz -C / \
    && echo /opt/libecwj2-3.3/lib > /etc/ld.so.conf.d/libecwj2.conf \
    && curl --retry 3 -fsSLO "https://github.com/OSGeo/gdal/releases/download/v${GDAL_VERSION}/gdal-${GDAL_VERSION}.tar.gz" \
    && echo "${GDAL_SHA256}  gdal-${GDAL_VERSION}.tar.gz" | sha256sum -c - \
    && tar xzf "gdal-${GDAL_VERSION}.tar.gz" \
    && cmake -S "gdal-${GDAL_VERSION}" -B out -DCMAKE_BUILD_TYPE=Release \
      -DGDAL_BUILD_OPTIONAL_DRIVERS=OFF -DOGR_BUILD_OPTIONAL_DRIVERS=OFF \
      -DGDAL_USE_ECW=ON -DGDAL_ENABLE_DRIVER_ECW=ON -DECW_ROOT=/opt/libecwj2-3.3 \
      -DBUILD_PYTHON_BINDINGS=OFF -DBUILD_TESTING=OFF \
    && cmake --build out -j"$(nproc)" \
    && cmake --install out \
    && ldconfig \
    && rm -rf /tmp/build

WORKDIR /data
