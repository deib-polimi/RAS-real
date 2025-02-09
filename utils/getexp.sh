#! /bin/bash
EXPDIR=$1
expfiles=$(ls $EXPDIR| grep -E '^exp-(tweet|ramp|sin|wiki)_(qn|ct|robust)-aws-graph\.py$' | while read -r file; do realpath "$EXPDIR/$file"; done)
export expfiles