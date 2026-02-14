# Statistical Analysis Guide

## Quick Start

### 1. Install Dependencies

```bash
pip3 install -r analysis_requirements.txt
```

Or install individually:
```bash
pip3 install numpy pandas scipy matplotlib seaborn openpyxl
```

### 2. Run Analysis

#### Single Run Analysis
```bash
python3 analyze_results.py results/ab_real_20260214_120000
```

#### Multiple Runs Analysis (Recommended)
```bash
python3 analyze_results.py results/ab_real_run1/ results/ab_real_run2/ results/ab_real_run3/
```

#### Using Wildcards
```bash
python3 analyze_results.py results/ab_real_*/
```

### 3. View Results

The script generates:

**Data Files:**
- `analysis_output/energy_summary.csv` - Energy consumption statistics
- `analysis_output/comparison_summary.csv` - Statistical comparisons between runtimes
- `analysis_output/performance_summary.csv` - Performance-energy trade-offs
- `analysis_output/analysis_results.xlsx` - All tables in one Excel file

**Visualizations:**
- `analysis_output/energy_boxplots.png` - Box plots showing distributions
- `analysis_output/energy_bars.png` - Bar charts with 95% CI error bars
- `analysis_output/power_timeseries.png` - Power consumption over time
- `analysis_output/efficiency_scatter.png` - Throughput vs energy per request

---

## What the Script Does

### Statistical Tests Performed

1. **Descriptive Statistics** (for each runtime × endpoint):
   - Mean, Standard Deviation, Median
   - 95% Confidence Intervals
   - Min, Max, Quartiles
   - Coefficient of Variation

2. **Normality Testing** (Shapiro-Wilk test):
   - Tests if data follows normal distribution
   - Determines which comparison test to use

3. **Variance Homogeneity** (Levene's test):
   - Tests if variances are equal between groups
   - Determines whether to use standard or Welch's t-test

4. **Group Comparisons**:
   - **Independent t-test** (if both groups normal, equal variance)
   - **Welch's t-test** (if both groups normal, unequal variance)
   - **Mann-Whitney U test** (if non-normal distribution)

5. **Effect Size** (Cohen's d):
   - Measures practical significance
   - Interpretation: small (0.2), medium (0.5), large (0.8)

### Metrics Calculated

**Energy Metrics:**
- Total energy consumption (Joules)
- Average power (Watts)
- Baseline-corrected values
- Energy per request (J/request)

**Performance Metrics:**
- Throughput (requests/second)
- Test duration
- Mean time per request

**Efficiency Metrics:**
- Energy per request
- Power consumption patterns
- Performance-energy trade-offs

---

## Understanding the Output

### Energy Summary Table

```
Runtime | Endpoint | Mean Energy (J) | SD (J) | 95% CI | Median (J) | CV (%) | N Runs
--------|----------|-----------------|--------|--------|------------|--------|--------
Spring  | CPU      | 245.30         | 12.10  | [237.8, 252.8] | 244.10 | 4.9  | 5
Node    | CPU      | 189.70         | 8.40   | [184.2, 195.2] | 188.90 | 4.4  | 5
```

**Interpretation:**
- Spring Boot uses **245.3J ± 12.1J** for CPU endpoint
- Node.js uses **189.7J ± 8.4J** for CPU endpoint
- Lower CV% means more consistent measurements

### Comparison Table

```
Endpoint | Spring Mean (J) | Node Mean (J) | Difference (J) | % Difference | Cohen's d | p-value | Significance
---------|-----------------|---------------|----------------|--------------|-----------|---------|-------------
CPU      | 245.30         | 189.70        | +55.60         | +29.3%       | 1.24      | 0.003   | ***
```

**Interpretation:**
- Spring uses **29.3% more energy** than Node.js for CPU workload
- Difference is **statistically significant** (p=0.003, ***)
- Effect size is **large** (d=1.24 > 0.8)
- This is practically meaningful, not just statistically significant

### Significance Levels

- `***` p < 0.001 (highly significant)
- `**` p < 0.01 (very significant)
- `*` p < 0.05 (significant)
- `ns` p ≥ 0.05 (not significant)

### Effect Size Interpretation

- **Negligible**: |d| < 0.2 (tiny difference)
- **Small**: 0.2 ≤ |d| < 0.5 (noticeable)
- **Medium**: 0.5 ≤ |d| < 0.8 (substantial)
- **Large**: |d| ≥ 0.8 (very substantial)

---

## For Your Dissertation

### Recommended Reporting Format (APA Style)

> "Java Spring Boot consumed significantly more energy (M = 245.3J, SD = 12.1J) than Node.js (M = 189.7J, SD = 8.4J) for the CPU-intensive endpoint, t(8) = 3.47, p = .003, d = 1.24, representing a 29.3% increase in energy consumption."

### Include in Your Report:

1. **Descriptive Statistics**: All means, SDs, and 95% CIs
2. **Effect Sizes**: Always report Cohen's d alongside p-values
3. **Test Assumptions**: Report normality and variance test results
4. **Visualizations**: Use box plots (show distributions) and bar charts (show means)
5. **Practical Significance**: Percentage differences and energy per request
6. **Limitations**: Acknowledge small sample size constraints (if applicable)

### Tables for Dissertation:

- Use `energy_summary.csv` → **Table 1** in your document
- Use `comparison_summary.csv` → **Table 2** in your document
- Use `performance_summary.csv` → **Table 3** in your document

### Figures for Dissertation:

- `energy_boxplots.png` → Shows data distribution and outliers
- `energy_bars.png` → Clean comparison with confidence intervals
- `power_timeseries.png` → Shows temporal behavior
- `efficiency_scatter.png` → Performance-energy trade-off visualization

---

## Troubleshooting

### "Module not found" Error
```bash
pip3 install -r analysis_requirements.txt
```

### No Data Found
- Check that CSV files exist: `test_<runtime>_<endpoint>.csv`
- Check that Apache Bench output exists: `ab_<runtime>_<endpoint>.txt`
- Verify results directory path is correct

### Python Version
Requires Python 3.8 or higher:
```bash
python3 --version
```

---

## Advanced Usage

### Custom Analysis

You can import the script as a module:

```python
from analyze_results import load_experiment_data, descriptive_stats, compare_groups

# Load your data
data = load_experiment_data("results/ab_real_20260214_120000")

# Access specific metrics
spring_cpu_energy = data['spring']['cpu']['corrected_energy']
node_cpu_energy = data['node']['cpu']['corrected_energy']

# Custom analysis
print(f"Spring CPU: {spring_cpu_energy:.2f}J")
print(f"Node CPU: {node_cpu_energy:.2f}J")
```

### Batch Analysis

To analyze multiple result directories automatically:

```bash
for dir in results/ab_real_*/; do
    echo "Analyzing: $dir"
    python3 analyze_results.py "$dir"
done
```

---

## References

The statistical methods used in this script follow:

- **Cohen, J.** (1988). Statistical Power Analysis for the Behavioral Sciences
- **APA Publication Manual** (7th ed.) - Statistical Reporting Guidelines
- **Jain, R.** (1991). The Art of Computer Systems Performance Analysis
- **IEEE 829-2008** Standard for Software Test Documentation

---

**Questions?** See [EXPERIMENTAL_DESIGN_STANDARDS.md](EXPERIMENTAL_DESIGN_STANDARDS.md) for detailed methodology and justification.
