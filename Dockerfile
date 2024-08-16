# Base image with Python 3.10 on Ubuntu 20.04
FROM python:3.10-slim AS base

# Set the working directory
WORKDIR /app

# Copy application files
COPY jphb /app/jphb
COPY main.py /app
COPY requirements.txt /app
COPY .env /app
COPY projects.json /app

# Install required packages, including Git, wget, and dependencies for srcml
RUN apt-get update && apt-get install -y \
    software-properties-common \
    git \
    wget \
    apt-transport-https \
    zip \
    unzip \
    cpio \
    man \
    lttng-tools\
    lttng-modules-dkms && \
    wget -q https://dlcdn.apache.org/maven/maven-3/3.9.8/binaries/apache-maven-3.9.8-bin.zip && \
    unzip apache-maven-3.9.8-bin.zip && \
    mv apache-maven-3.9.8 /usr/local && \
    rm apache-maven-3.9.8-bin.zip && \
    ln -s /usr/local/apache-maven-3.9.8/bin/mvn /usr/bin/mvn && \
    wget -q http://archive.ubuntu.com/ubuntu/pool/main/libx/libxslt/libxslt1.1_1.1.34-4ubuntu0.22.04.1_amd64.deb && \
    apt-get install -y ./libxslt1.1_1.1.34-4ubuntu0.22.04.1_amd64.deb --fix-missing && \
    rm libxslt1.1_1.1.34-4ubuntu0.22.04.1_amd64.deb && \
    wget -q http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb && \
    dpkg -i libssl1.1_1.1.0g-2ubuntu4_amd64.deb && \
    rm libssl1.1_1.1.0g-2ubuntu4_amd64.deb && \
    wget -q http://131.123.42.38/lmcrs/v1.0.0/srcml_1.0.0-1_ubuntu20.04.deb && \
    apt-get install -y ./srcml_1.0.0-1_ubuntu20.04.deb && \
    rm srcml_1.0.0-1_ubuntu20.04.deb && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Stage for Java 8
FROM openjdk:8-jdk-slim AS jdk8

# Stage for Java 11
FROM openjdk:11-jdk-slim AS jdk11

# Stage for Java 17
FROM openjdk:17-jdk-slim AS jdk17

# Stage for Java 21 (using the latest available version as of now)
FROM openjdk:21-jdk-slim AS jdk21

# Copy JDKs to the base image with specified paths
FROM base
COPY --from=jdk8 /usr/local/openjdk-8 /usr/lib/jvm/java-8-openjdk-amd64
COPY --from=jdk11 /usr/local/openjdk-11 /usr/lib/jvm/java-11-openjdk-amd64
COPY --from=jdk17 /usr/local/openjdk-17 /usr/lib/jvm/java-17-openjdk-amd64
COPY --from=jdk21 /usr/local/openjdk-21 /usr/lib/jvm/java-21-openjdk-amd64

# Set the default Java version (change as needed)
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:/usr/local/bin:${PATH}"

# Run main.py when the container launches
ENTRYPOINT ["python", "main.py"]