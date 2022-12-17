#!/bin/bash

# Check if the required number of arguments have been provided
if [ $# -lt 2 ]
then
  echo "Usage: $0 FILE N"
  exit 1
fi

FILE=$1
N=$2

# Repeat the commands N times
for i in $(seq 1 $N)
do
  git pull --rebase
  taskset -c 25-31 locust --headless -f "$FILE"
  git add -A
  git commit -am 'aws-exp'
  git push
done
