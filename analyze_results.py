#!/usr/bin/env python3
"""
Statistical Analysis Script for Runtime Energy Efficiency Experiment

This script analyzes power consumption data from multiple experimental runs,
comparing Java Spring Boot vs Node.js energy efficiency across different workload types.

Usage:
    python3 analyze_results.py <results_dir1> [<results_dir2> ...]

Requirements:
    pip install numpy pandas scipy matplotlib seaborn openpyxl
"""

import os
import sys
import csv
import glob
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Tuple

# Set plotting style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10

# ============================================================================
# CONFIGURATION
# ============================================================================

RUNTIMES = ["spring", "node"]
ENDPOINTS = ["cpu", "memory", "io", "mixed"]
ALPHA = 0.05  # Significance level
CONFIDENCE_LEVEL = 0.95


# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_power_data(csv_file: str) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Load power measurements from CSV file.
    
    Returns:
        timestamps, voltages, currents, powers, duration
    """
    timestamps = []
    voltages = []
    currents = []
    powers = []
    
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamps.append(float(row['timestamp']))
            voltages.append(float(row['voltage_V']))
            currents.append(float(row['current_A']))
            powers.append(float(row['power_W']))
    
    timestamps = np.array(timestamps)
    voltages = np.array(voltages)
    currents = np.array(currents)
    powers = np.array(powers)
    
    duration = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0
    
    return timestamps, voltages, currents, powers, duration


def compute_energy(timestamps: np.ndarray, powers: np.ndarray) -> float:
    """Compute total energy using trapezoidal integration.

    Energy (J) = integral of Power (W) over time (s).

    Implemented manually instead of using ``np.trapz`` to avoid
    version-specific NumPy API differences.
    """
    if len(timestamps) < 2:
        return 0.0

    dt = timestamps[1:] - timestamps[:-1]
    avg_power = (powers[1:] + powers[:-1]) * 0.5
    energy = float(np.sum(avg_power * dt))
    return energy


def parse_ab_output(ab_file: str) -> Dict:
    """
    Parse Apache Bench output file for performance metrics.
    
    Returns dict with: completed_requests, failed_requests, duration, 
                       requests_per_sec, mean_time_per_request
    """
    results = {
        'completed_requests': 0,
        'failed_requests': 0,
        'duration_s': 0.0,
        'requests_per_sec': 0.0,
        'mean_time_per_request_ms': 0.0
    }
    
    try:
        with open(ab_file, 'r') as f:
            content = f.read()
            
            # Parse key metrics using regex
            import re
            
            match = re.search(r'Complete requests:\s+(\d+)', content)
            if match:
                results['completed_requests'] = int(match.group(1))
            
            match = re.search(r'Failed requests:\s+(\d+)', content)
            if match:
                results['failed_requests'] = int(match.group(1))
            
            match = re.search(r'Time taken for tests:\s+([\d.]+)', content)
            if match:
                results['duration_s'] = float(match.group(1))
            
            match = re.search(r'Requests per second:\s+([\d.]+)', content)
            if match:
                results['requests_per_sec'] = float(match.group(1))
            
            match = re.search(r'Time per request:\s+([\d.]+).*\(mean\)', content)
            if match:
                results['mean_time_per_request_ms'] = float(match.group(1))
    
    except Exception as e:
        print(f"Warning: Could not parse {ab_file}: {e}")
    
    return results


def load_experiment_data(results_dir: str) -> Dict:
    """
    Load all data from a single experiment run.
    
    Returns nested dict: data[runtime][endpoint] = {energy, power_data, performance, ...}
    """
    data = {runtime: {} for runtime in RUNTIMES}
    
    results_path = Path(results_dir)
    
    # Load baseline data
    baseline_files = list(results_path.glob("baseline*.csv"))
    baseline_power = None
    if baseline_files:
        _, _, _, powers, _ = load_power_data(str(baseline_files[0]))
        baseline_power = np.mean(powers)
        print(f"  Baseline power: {baseline_power:.3f} W")
    
    # Load test data for each runtime and endpoint
    for runtime in RUNTIMES:
        for endpoint in ENDPOINTS:
            # Load power data
            test_csv = results_path / f"test_{runtime}_{endpoint}.csv"
            if not test_csv.exists():
                continue
            
            timestamps, voltages, currents, powers, duration = load_power_data(str(test_csv))
            
            # Compute energy
            total_energy = compute_energy(timestamps, powers)
            avg_power = np.mean(powers)
            
            # Baseline correction if available
            corrected_energy = total_energy
            corrected_power = avg_power
            if baseline_power is not None:
                baseline_energy = baseline_power * duration
                corrected_energy = total_energy - baseline_energy
                corrected_power = avg_power - baseline_power
            
            # Load performance data
            ab_file = results_path / f"ab_{runtime}_{endpoint}.txt"
            performance = parse_ab_output(str(ab_file)) if ab_file.exists() else {}
            
            # Calculate energy per request
            energy_per_request = 0.0
            if performance.get('completed_requests', 0) > 0:
                energy_per_request = corrected_energy / performance['completed_requests']
            
            # Store all data
            data[runtime][endpoint] = {
                'timestamps': timestamps,
                'powers': powers,
                'duration': duration,
                'total_energy': total_energy,
                'avg_power': avg_power,
                'corrected_energy': corrected_energy,
                'corrected_power': corrected_power,
                'peak_power': np.max(powers),
                'energy_per_request': energy_per_request,
                'performance': performance,
                'n_samples': len(powers)
            }
    
    return data


# ============================================================================
# STATISTICAL ANALYSIS FUNCTIONS
# ============================================================================

def descriptive_stats(data: np.ndarray) -> Dict:
    """
    Calculate descriptive statistics for a dataset.
    """
    n = len(data)
    mean = np.mean(data)
    std = np.std(data, ddof=1)
    sem = stats.sem(data)
    ci = stats.t.interval(CONFIDENCE_LEVEL, n-1, loc=mean, scale=sem)
    
    return {
        'n': n,
        'mean': mean,
        'std': std,
        'sem': sem,
        'median': np.median(data),
        'min': np.min(data),
        'max': np.max(data),
        'ci_lower': ci[0],
        'ci_upper': ci[1],
        'cv': (std / mean * 100) if mean != 0 else 0,  # Coefficient of variation
        'q25': np.percentile(data, 25),
        'q75': np.percentile(data, 75)
    }


def cohen_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """
    Calculate Cohen's d effect size.
    
    Interpretation:
        |d| < 0.2: negligible
        |d| < 0.5: small
        |d| < 0.8: medium
        |d| >= 0.8: large
    """
    n1, n2 = len(group1), len(group2)
    var1 = np.var(group1, ddof=1)
    var2 = np.var(group2, ddof=1)
    
    # Pooled standard deviation
    pooled_std = np.sqrt(((n1-1)*var1 + (n2-1)*var2) / (n1+n2-2))
    
    if pooled_std == 0:
        return 0.0
    
    return (np.mean(group1) - np.mean(group2)) / pooled_std


def effect_size_interpretation(d: float) -> str:
    """Return interpretation of Cohen's d."""
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    elif abs_d < 0.5:
        return "small"
    elif abs_d < 0.8:
        return "medium"
    else:
        return "large"


def compare_groups(group1: np.ndarray, group2: np.ndarray, 
                   group1_name: str, group2_name: str) -> Dict:
    """
    Statistical comparison between two groups.
    
    Performs:
    - Normality tests (Shapiro-Wilk)
    - Variance homogeneity test (Levene)
    - Appropriate comparison test (t-test or Mann-Whitney U)
    - Effect size (Cohen's d)
    """
    results = {
        'group1_name': group1_name,
        'group2_name': group2_name,
        'group1_n': len(group1),
        'group2_n': len(group2),
        'group1_mean': np.mean(group1),
        'group2_mean': np.mean(group2),
        'difference': np.mean(group1) - np.mean(group2),
        'percent_diff': ((np.mean(group1) - np.mean(group2)) / np.mean(group2) * 100) 
                        if np.mean(group2) != 0 else 0
    }
    
    # Normality tests
    if len(group1) >= 3:
        stat1, p1 = stats.shapiro(group1)
        results['group1_normality_p'] = p1
        results['group1_normal'] = p1 > ALPHA
    else:
        results['group1_normal'] = None
    
    if len(group2) >= 3:
        stat2, p2 = stats.shapiro(group2)
        results['group2_normality_p'] = p2
        results['group2_normal'] = p2 > ALPHA
    else:
        results['group2_normal'] = None
    
    # Variance homogeneity test
    if results['group1_normal'] and results['group2_normal']:
        stat_lev, p_lev = stats.levene(group1, group2)
        results['levene_p'] = p_lev
        results['equal_variance'] = p_lev > ALPHA
    else:
        results['equal_variance'] = None
    
    # Choose appropriate test
    if results['group1_normal'] and results['group2_normal']:
        # Both normal - use t-test
        if results['equal_variance']:
            # Equal variance - standard t-test
            stat, p = stats.ttest_ind(group1, group2)
            results['test_used'] = "Independent t-test"
        else:
            # Unequal variance - Welch's t-test
            stat, p = stats.ttest_ind(group1, group2, equal_var=False)
            results['test_used'] = "Welch's t-test"
        
        results['test_statistic'] = stat
        results['p_value'] = p
        results['df'] = len(group1) + len(group2) - 2
    else:
        # Non-normal - use Mann-Whitney U test
        stat, p = stats.mannwhitneyu(group1, group2, alternative='two-sided')
        results['test_used'] = "Mann-Whitney U test"
        results['test_statistic'] = stat
        results['p_value'] = p
        results['df'] = None
    
    # Effect size
    results['cohen_d'] = cohen_d(group1, group2)
    results['effect_size'] = effect_size_interpretation(results['cohen_d'])
    
    # Significance
    results['significant'] = results['p_value'] < ALPHA
    if results['p_value'] < 0.001:
        results['sig_stars'] = '***'
    elif results['p_value'] < 0.01:
        results['sig_stars'] = '**'
    elif results['p_value'] < 0.05:
        results['sig_stars'] = '*'
    else:
        results['sig_stars'] = 'ns'
    
    return results


# ============================================================================
# AGGREGATION ACROSS MULTIPLE RUNS
# ============================================================================

def aggregate_multiple_runs(all_runs_data: List[Dict]) -> Dict:
    """
    Aggregate data from multiple experimental runs.
    
    Returns aggregated data structure with statistics across runs.
    """
    aggregated = {}
    
    for runtime in RUNTIMES:
        aggregated[runtime] = {}
        for endpoint in ENDPOINTS:
            # Collect values across all runs
            corrected_energies = []
            corrected_powers = []
            energy_per_requests = []
            throughputs = []
            durations = []
            
            for run_data in all_runs_data:
                if endpoint in run_data[runtime]:
                    d = run_data[runtime][endpoint]
                    corrected_energies.append(d['corrected_energy'])
                    corrected_powers.append(d['corrected_power'])
                    energy_per_requests.append(d['energy_per_request'])
                    
                    perf = d['performance']
                    if perf.get('requests_per_sec', 0) > 0:
                        throughputs.append(perf['requests_per_sec'])
                    if perf.get('duration_s', 0) > 0:
                        durations.append(perf['duration_s'])
            
            if corrected_energies:
                aggregated[runtime][endpoint] = {
                    'energy': descriptive_stats(np.array(corrected_energies)),
                    'power': descriptive_stats(np.array(corrected_powers)),
                    'energy_per_request': descriptive_stats(np.array(energy_per_requests)) 
                                          if energy_per_requests else None,
                    'throughput': descriptive_stats(np.array(throughputs)) 
                                 if throughputs else None,
                    'duration': descriptive_stats(np.array(durations)) 
                               if durations else None,
                    'n_runs': len(corrected_energies),
                    'raw_energies': corrected_energies,
                    'raw_powers': corrected_powers
                }
    
    return aggregated


# ============================================================================
# REPORTING FUNCTIONS
# ============================================================================

def create_summary_tables(aggregated_data: Dict, comparisons: Dict) -> pd.DataFrame:
    """
    Create comprehensive summary tables as DataFrames.
    """
    # Table 1: Energy Consumption Summary
    rows = []
    for runtime in RUNTIMES:
        for endpoint in ENDPOINTS:
            if endpoint in aggregated_data[runtime]:
                d = aggregated_data[runtime][endpoint]
                energy = d['energy']
                rows.append({
                    'Runtime': runtime.capitalize(),
                    'Endpoint': endpoint.upper(),
                    'Mean Energy (J)': f"{energy['mean']:.2f}",
                    'SD (J)': f"{energy['std']:.2f}",
                    '95% CI': f"[{energy['ci_lower']:.2f}, {energy['ci_upper']:.2f}]",
                    'Median (J)': f"{energy['median']:.2f}",
                    'CV (%)': f"{energy['cv']:.1f}",
                    'N Runs': d['n_runs']
                })
    
    df_energy = pd.DataFrame(rows)
    
    # Table 2: Comparison Summary
    rows = []
    for endpoint in ENDPOINTS:
        if endpoint in comparisons:
            comp = comparisons[endpoint]
            rows.append({
                'Endpoint': endpoint.upper(),
                f"{comp['group1_name']} Mean (J)": f"{comp['group1_mean']:.2f}",
                f"{comp['group2_name']} Mean (J)": f"{comp['group2_mean']:.2f}",
                'Difference (J)': f"{comp['difference']:+.2f}",
                '% Difference': f"{comp['percent_diff']:+.1f}%",
                "Cohen's d": f"{comp['cohen_d']:.2f}",
                'Effect Size': comp['effect_size'],
                'p-value': f"{comp['p_value']:.4f}",
                'Significance': comp['sig_stars'],
                'Test Used': comp['test_used']
            })
    
    df_comparison = pd.DataFrame(rows)
    
    # Table 3: Performance-Energy Trade-off
    rows = []
    for runtime in RUNTIMES:
        for endpoint in ENDPOINTS:
            if endpoint in aggregated_data[runtime]:
                d = aggregated_data[runtime][endpoint]
                if d['throughput'] and d['energy_per_request']:
                    rows.append({
                        'Runtime': runtime.capitalize(),
                        'Endpoint': endpoint.upper(),
                        'Throughput (req/s)': f"{d['throughput']['mean']:.1f} ± {d['throughput']['std']:.1f}",
                        'Energy per Request (J/req)': f"{d['energy_per_request']['mean']:.4f} ± {d['energy_per_request']['std']:.4f}",
                        'Duration (s)': f"{d['duration']['mean']:.1f} ± {d['duration']['std']:.1f}"
                    })
    
    df_performance = pd.DataFrame(rows)
    
    return df_energy, df_comparison, df_performance


def export_results(df_energy: pd.DataFrame, df_comparison: pd.DataFrame, 
                   df_performance: pd.DataFrame, output_dir: str):
    """
    Export results to CSV and Excel files.
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Export to CSV
    df_energy.to_csv(output_path / 'energy_summary.csv', index=False)
    df_comparison.to_csv(output_path / 'comparison_summary.csv', index=False)
    df_performance.to_csv(output_path / 'performance_summary.csv', index=False)
    
    # Export to single Excel file with multiple sheets
    with pd.ExcelWriter(output_path / 'analysis_results.xlsx') as writer:
        df_energy.to_excel(writer, sheet_name='Energy Summary', index=False)
        df_comparison.to_excel(writer, sheet_name='Comparison', index=False)
        df_performance.to_excel(writer, sheet_name='Performance', index=False)
    
    print(f"\n✓ Results exported to: {output_path}")


# ============================================================================
# VISUALIZATION FUNCTIONS
# ============================================================================

def plot_energy_comparison(aggregated_data: Dict, output_dir: str):
    """
    Create box plots comparing energy consumption.
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    
    for idx, endpoint in enumerate(ENDPOINTS):
        ax = axes[idx]
        
        data_to_plot = []
        labels = []
        
        for runtime in RUNTIMES:
            if endpoint in aggregated_data[runtime]:
                data_to_plot.append(aggregated_data[runtime][endpoint]['raw_energies'])
                labels.append(runtime.capitalize())
        
        if data_to_plot:
            bp = ax.boxplot(data_to_plot, labels=labels, patch_artist=True)
            
            # Color the boxes
            colors = ['#ff9999', '#66b3ff']
            for patch, color in zip(bp['boxes'], colors):
                patch.set_facecolor(color)
            
            ax.set_title(f'{endpoint.upper()} Endpoint', fontsize=12, fontweight='bold')
            ax.set_ylabel('Energy Consumption (J)', fontsize=10)
            ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'energy_boxplots.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✓ Created: energy_boxplots.png")


def plot_energy_bars(aggregated_data: Dict, output_dir: str):
    """
    Create bar charts with error bars for energy consumption.
    """
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(ENDPOINTS))
    width = 0.35
    
    spring_means = []
    spring_cis = []
    node_means = []
    node_cis = []
    
    for endpoint in ENDPOINTS:
        if endpoint in aggregated_data['spring']:
            energy_spring = aggregated_data['spring'][endpoint]['energy']
            spring_means.append(energy_spring['mean'])
            ci_width = energy_spring['ci_upper'] - energy_spring['mean']
            spring_cis.append(ci_width)
        else:
            spring_means.append(0)
            spring_cis.append(0)
        
        if endpoint in aggregated_data['node']:
            energy_node = aggregated_data['node'][endpoint]['energy']
            node_means.append(energy_node['mean'])
            ci_width = energy_node['ci_upper'] - energy_node['mean']
            node_cis.append(ci_width)
        else:
            node_means.append(0)
            node_cis.append(0)
    
    ax.bar(x - width/2, spring_means, width, yerr=spring_cis, 
           label='Spring Boot', color='#ff9999', capsize=5)
    ax.bar(x + width/2, node_means, width, yerr=node_cis, 
           label='Node.js', color='#66b3ff', capsize=5)
    
    ax.set_xlabel('Endpoint', fontsize=11, fontweight='bold')
    ax.set_ylabel('Energy Consumption (J)', fontsize=11, fontweight='bold')
    ax.set_title('Energy Consumption Comparison with 95% CI', fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([e.upper() for e in ENDPOINTS])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'energy_bars.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✓ Created: energy_bars.png")


def plot_time_series(all_runs_data: List[Dict], output_dir: str):
    """
    Create time series plots of power consumption.
    """
    # Plot first run only (to avoid clutter)
    if not all_runs_data:
        return
    
    run_data = all_runs_data[0]
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    
    for idx, endpoint in enumerate(ENDPOINTS):
        ax = axes[idx]
        
        for runtime in RUNTIMES:
            if endpoint in run_data[runtime]:
                d = run_data[runtime][endpoint]
                timestamps = d['timestamps']
                powers = d['powers']
                
                # Normalize timestamps to start at 0
                t = timestamps - timestamps[0]
                
                label = f"{runtime.capitalize()} (avg: {d['corrected_power']:.2f}W)"
                ax.plot(t, powers, label=label, alpha=0.7, linewidth=1.5)
        
        ax.set_title(f'{endpoint.upper()} Endpoint', fontsize=12, fontweight='bold')
        ax.set_xlabel('Time (s)', fontsize=10)
        ax.set_ylabel('Power (W)', fontsize=10)
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.suptitle('Power Consumption Over Time (First Run)', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'power_timeseries.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✓ Created: power_timeseries.png")


def plot_efficiency_scatter(aggregated_data: Dict, output_dir: str):
    """
    Create scatter plot of throughput vs energy per request.
    """
    fig, ax = plt.subplots(figsize=(10, 7))
    
    colors = {'spring': '#ff9999', 'node': '#66b3ff'}
    markers = {'cpu': 'o', 'memory': 's', 'io': '^', 'mixed': 'D'}
    
    for runtime in RUNTIMES:
        for endpoint in ENDPOINTS:
            if endpoint in aggregated_data[runtime]:
                d = aggregated_data[runtime][endpoint]
                if d['throughput'] and d['energy_per_request']:
                    x = d['throughput']['mean']
                    y = d['energy_per_request']['mean']
                    
                    ax.scatter(x, y, s=150, c=colors[runtime], 
                             marker=markers[endpoint], alpha=0.7,
                             label=f"{runtime.capitalize()} - {endpoint.upper()}")
    
    ax.set_xlabel('Throughput (requests/s)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Energy per Request (J/req)', fontsize=11, fontweight='bold')
    ax.set_title('Energy Efficiency: Throughput vs Energy per Request', 
                fontsize=13, fontweight='bold')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'efficiency_scatter.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("✓ Created: efficiency_scatter.png")


# ============================================================================
# MAIN ANALYSIS PIPELINE
# ============================================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_results.py <results_dir1> [<results_dir2> ...]")
        print("\nExample:")
        print("  python3 analyze_results.py results/ab_real_20260214_120000")
        print("  python3 analyze_results.py results/ab_real_*/")
        sys.exit(1)
    
    result_dirs = sys.argv[1:]
    
    print("=" * 70)
    print("RUNTIME ENERGY EFFICIENCY ANALYSIS")
    print("=" * 70)
    print(f"\nAnalyzing {len(result_dirs)} experimental run(s)...\n")
    
    # Load data from all runs
    all_runs_data = []
    for i, results_dir in enumerate(result_dirs, 1):
        print(f"Loading run {i}: {results_dir}")
        data = load_experiment_data(results_dir)
        all_runs_data.append(data)
    
    if not all_runs_data:
        print("Error: No data loaded!")
        sys.exit(1)
    
    print(f"\n✓ Loaded {len(all_runs_data)} run(s) successfully\n")
    
    # Aggregate data across runs
    print("Aggregating data across runs...")
    aggregated_data = aggregate_multiple_runs(all_runs_data)
    
    # Perform comparisons between runtimes for each endpoint
    print("Performing statistical comparisons...")
    comparisons = {}
    for endpoint in ENDPOINTS:
        if (endpoint in aggregated_data['spring'] and 
            endpoint in aggregated_data['node']):
            
            spring_energies = np.array(aggregated_data['spring'][endpoint]['raw_energies'])
            node_energies = np.array(aggregated_data['node'][endpoint]['raw_energies'])
            
            comp = compare_groups(spring_energies, node_energies, 
                                 'Spring', 'Node.js')
            comparisons[endpoint] = comp
            
            print(f"  {endpoint.upper()}: {comp['test_used']}, "
                  f"p={comp['p_value']:.4f} {comp['sig_stars']}, "
                  f"d={comp['cohen_d']:.2f} ({comp['effect_size']})")
    
    # Create output directory
    output_dir = "analysis_output"
    Path(output_dir).mkdir(exist_ok=True)
    
    # Generate summary tables
    print("\nGenerating summary tables...")
    df_energy, df_comparison, df_performance = create_summary_tables(
        aggregated_data, comparisons)
    
    # Export results
    export_results(df_energy, df_comparison, df_performance, output_dir)
    
    # Print tables to console
    print("\n" + "=" * 70)
    print("ENERGY CONSUMPTION SUMMARY")
    print("=" * 70)
    print(df_energy.to_string(index=False))
    
    print("\n" + "=" * 70)
    print("STATISTICAL COMPARISON")
    print("=" * 70)
    print(df_comparison.to_string(index=False))
    
    if not df_performance.empty:
        print("\n" + "=" * 70)
        print("PERFORMANCE-ENERGY TRADE-OFF")
        print("=" * 70)
        print(df_performance.to_string(index=False))
    
    # Generate visualizations
    print("\nGenerating visualizations...")
    plot_energy_comparison(aggregated_data, output_dir)
    plot_energy_bars(aggregated_data, output_dir)
    plot_time_series(all_runs_data, output_dir)
    plot_efficiency_scatter(aggregated_data, output_dir)
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE!")
    print("=" * 70)
    print(f"\nAll results saved to: {output_dir}/")
    print("  - energy_summary.csv")
    print("  - comparison_summary.csv")
    print("  - performance_summary.csv")
    print("  - analysis_results.xlsx")
    print("  - energy_boxplots.png")
    print("  - energy_bars.png")
    print("  - power_timeseries.png")
    print("  - efficiency_scatter.png")
    print("\nSignificance levels: *** p<0.001, ** p<0.01, * p<0.05, ns=not significant")
    print("Effect sizes: negligible (<0.2), small (<0.5), medium (<0.8), large (≥0.8)")
    print()


if __name__ == "__main__":
    main()
