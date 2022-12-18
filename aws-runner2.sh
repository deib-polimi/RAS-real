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

# Calculate the number of CPUs TOT available on the system
TOT_CPUS=$(nproc)
echo $TOT_CPUS
echo $CPUS

# Set the range for the taskset command
CPU_RANGE=$(($TOT_CPUS-$CPUS))-$(($TOT_CPUS-1))

# Repeat the commands N times
for i in $(seq 1 $N)
do
  #git pull --rebase
  echo $CPU_RANGE
  echo $FILE
  #taskset -c $CPU_RANGE locust --headless -f $FILE
  #git add -A
  #git commit -am 'aws-exp'
  #git push
done
