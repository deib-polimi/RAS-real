#! /bin/bash
EXPDIR=$1
export expfiles=$(ls $EXPDIR| grep -E '^exp-(tweet|ramp|sin|wiki)_(qn|ct|robust)-aws-graph\.py$' | while read -r file; do realpath "$file"; done)