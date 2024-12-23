 #!/bin/bash

# Check if the required number of arguments have been provided
if [ $# -lt 3 ]
then
  echo "Usage: $0 REPETITIONS LOCUST_CPUS LOCUSTFILE1 LOCUSTFILE2 LOCUSTFILE3 ..."
  echo "Example: $0 1 25-31 locustfiles/exp-ramp_rule-aws.py locustfiles/exp-ramp_rule3-aws.py"
  exit 1
fi

N=$1
CPU_RANGE=$2
shift 2

# Loop through all remaining arguments
for file in "$@"
do
   ./aws-runner.sh $file $N $CPU_RANGE 
done 
