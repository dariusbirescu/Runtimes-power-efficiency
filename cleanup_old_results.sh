#!/bin/bash
# Clean up old result files (not in folders)
rm -f baseline_mocked_*.csv
rm -f test_*_mocked_*.csv
rm -rf results_mocked_*
echo "✓ Cleaned up old result files"
