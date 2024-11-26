#!/bin/bash

# Check if the required number of arguments have been provided
if [ $# -lt 3 ]
then
  echo "Usage: $0 LOCUST_FILE REPETITIONS LOCUST_CPUS"
  exit 1
fi

FILE=$1
N=$2
CPUS=$3


# Repeat the commands N times
for i in $(seq 1 $N)
do
  git pull --rebase
  echo $CPUS
  echo $FILE
  taskset -c $CPUS locust --headless -f $FILE
  git add -A
  git commit -am 'aws-exp'
  git pull --rebase
  git push
  echo "waiting two mins"
  sleep 2m
  echo "restarting"
done
