#!/bin/zsh
cd "$(dirname "$0")"
./suite.sh run1 audits > suite-run1.txt 2>&1; r1=$?
./suite.sh run2 > suite-run2.txt 2>&1; r2=$?
echo "CHAIN run1=$r1 run2=$r2" > chain-exit.txt
[ $r1 -eq 0 ] && [ $r2 -eq 0 ]
