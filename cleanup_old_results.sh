#!/bin/bash
# Clean up old result files (not in folders)
rm -f baseline_AVJWData_*.csv
rm -f test_*_AVJWData_*.csv
rm -f wrk_*_AVJWData_*.txt
rm -f results_AVJWData.tex
rm -f testfile.txt
rm -rf results_AVJWData_*
rm -rf results_2026*
echo "✓ Cleaned up old result files"
