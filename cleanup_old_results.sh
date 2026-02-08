#!/bin/bash
# Clean up old result files (not in folders)
rm -f baseline_mocked_*.csv
rm -f test_*_mocked_*.csv
rm -f wrk_*_mocked_*.txt
rm -f results_mocked.tex
rm -f testfile.txt
rm -rf results_mocked_*
rm -rf results_2026*
echo "✓ Cleaned up old result files"
