#!/bin/bash
# Clean up old result files (not in folders)
rm -f baseline_cvadataed_*.csv
rm -f test_*_cvadataed_*.csv
rm -f wrk_*_cvadataed_*.txt
rm -f results_cvadataed.tex
rm -f testfile.txt
rm -rf results_cvadataed_*
rm -rf results_2026*
echo "✓ Cleaned up old result files"
