#!/bin/bash

# Array of project names
projects=(
    # "HdrHistogram"
    # "JCTools"
    # "debezium"
    "SimpleFlatMapper"
    "objenesis"
    "apm-agent-java"
    "jetty"
    "netty"
    "rdf4j"
    "zipkin"
    "client_java"
    "Chronicle-Core"
    # # "logbook"
    "fastjson2"
    "log4j2"
    # # "cantaloupe"
    "jdbi"
    # # "jooby"
    # "feign"
    # # "panda"
    "protostuff"
    # # "hadoop"
    # # "camel"
    # # "kafka"
    # # "cassandra"
    # # "spark"
)

# Loop through each project and run the command
for project in "${projects[@]}"; do
    echo "Running: python main.py $project"
    python main.py "$project"
    echo "----------------------------------------"
done

echo "All projects have been processed."