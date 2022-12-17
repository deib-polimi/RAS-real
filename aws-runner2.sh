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

N=$1

# Calculate the number of CPUs TOT available on the system
TOT_CPUS=$(nproc)

# Set the range for the taskset command
CPU_RANGE=$(($TOT_CPUS-$N-1))-$(($TOT_CPUS-1))

# Repeat the commands N times
for i in $(seq 1 $N)
do
  #git pull --rebase
  echo 'taskset -c RANGE locust --headless -f "$FILE"'
  #git add -A
  #git commit -am 'aws-exp'
  #git push
done
