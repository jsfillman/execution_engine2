#!/usr/bin/env bash
set -x
docker build -f DockerfileForCondor . -t kbase/ee2:local_condor
docker build -f DockerfileForInterpreter . -t kbase/ee2:local_interpreter
docker-compose up -d 
