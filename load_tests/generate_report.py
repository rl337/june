#!/usr/bin/env python3
"""
Generate comprehensive load test reports with metrics analysis and comparisons.
"""
import json
import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sns.set_style("whitegrid")


def load_locust_json(json_path: Path) -> dict:
    """Load Locust JSON report."""
    with open(json_path, 'r') as f:
        return json.load(f)


def generate_metrics_report(locust_data: dict, output_path: Path):
    """Generate metrics report from Locust data."""
    stats = locust_data.get("stats", [])
    
    metrics = {
        "total_requests": locust_data.get("total_requests", 0),
        "total_failures": locust_data.get("total_failures", 0),
        "total_rps": locust_data.get("total_rps", 0),
        "fail_ratio": locust_data.get("fail_ratio", 0),
    }
    
    # Extract endpoint-specific metrics
    endpoints = []
    for stat in stats:
        if stat.get("name") != "Aggregated":
            endpoints.append({
                "name": stat.get("name"),
                "method": stat.get("method", "GET"),
                "num_requests": stat.get("num_requests", 0),
                "num_failures": stat.get("num_failures", 0),
                "avg_response_time": stat.get("avg_response_time", 0),
                "min_response_time": stat.get("min_response_time", 0),
                "max_response_time": stat.get("max_response_time", 0),
                "median_response_time": stat.get("median_response_time", 0),
                "p95_response_time": stat.get("p95_response_time", 0),
                "p99_response_time": stat.get("p99_response_time", 0),
            })
    
    # Create DataFrame
    df = pd.DataFrame(endpoints)
    
    # Save CSV
    csv_path = output_path / "metrics.csv"
    df.to_csv(csv_path, index=False)
    logger.info(f"Saved metrics CSV to {csv_path}")
    
    # Generate charts
    generate_charts(df, metrics, output_path)
    
    # Generate summary report
    generate_summary_report(metrics, df, output_path)
    
    return metrics, df


def generate_charts(df: pd.DataFrame, metrics: dict, output_path: Path):
    """Generate visualization charts."""
    if df.empty:
        logger.warning("No data to generate charts")
        return
    
    # Response time by endpoint
    plt.figure(figsize=(12, 6))
    df_sorted = df.sort_values("avg_response_time", ascending=False)
    plt.barh(df_sorted["name"], df_sorted["avg_response_time"])
    plt.xlabel("Average Response Time (ms)")
    plt.title("Average Response Time by Endpoint")
    plt.tight_layout()
    plt.savefig(output_path / "response_time_by_endpoint.png", dpi=150)
    plt.close()
    
    # P95 response time
    plt.figure(figsize=(12, 6))
    df_sorted = df.sort_values("p95_response_time", ascending=False)
    plt.barh(df_sorted["name"], df_sorted["p95_response_time"])
    plt.xlabel("P95 Response Time (ms)")
    plt.title("P95 Response Time by Endpoint")
    plt.axvline(x=2000, color='r', linestyle='--', label='Target (2s)')
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path / "p95_response_time.png", dpi=150)
    plt.close()
    
    # Error rate by endpoint
    if "num_failures" in df.columns and "num_requests" in df.columns:
        df["error_rate"] = (df["num_failures"] / df["num_requests"] * 100).fillna(0)
        plt.figure(figsize=(12, 6))
        df_sorted = df.sort_values("error_rate", ascending=False)
        plt.barh(df_sorted["name"], df_sorted["error_rate"])
        plt.xlabel("Error Rate (%)")
        plt.title("Error Rate by Endpoint")
        plt.axvline(x=1, color='r', linestyle='--', label='Threshold (1%)')
        plt.legend()
        plt.tight_layout()
        plt.savefig(output_path / "error_rate_by_endpoint.png", dpi=150)
        plt.close()
    
    # Request distribution
    plt.figure(figsize=(12, 6))
    df_sorted = df.sort_values("num_requests", ascending=False)
    plt.barh(df_sorted["name"], df_sorted["num_requests"])
    plt.xlabel("Number of Requests")
    plt.title("Request Distribution by Endpoint")
    plt.tight_layout()
    plt.savefig(output_path / "request_distribution.png", dpi=150)
    plt.close()


def generate_summary_report(metrics: dict, df: pd.DataFrame, output_path: Path):
    """Generate text summary report."""
    report_path = output_path / "summary.txt"
    
    with open(report_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Load Test Summary Report\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        
        f.write("Overall Metrics:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Requests: {metrics['total_requests']:,}\n")
        f.write(f"Total Failures: {metrics['total_failures']:,}\n")
        f.write(f"Success Rate: {(1 - metrics['fail_ratio']) * 100:.2f}%\n")
        f.write(f"Requests per Second: {metrics['total_rps']:.2f}\n\n")
        
        if not df.empty:
            f.write("Endpoint Performance:\n")
            f.write("-" * 80 + "\n")
            f.write(f"{'Endpoint':<40} {'Avg RT (ms)':<15} {'P95 (ms)':<15} {'Errors':<10}\n")
            f.write("-" * 80 + "\n")
            
            for _, row in df.iterrows():
                error_count = int(row.get("num_failures", 0))
                f.write(
                    f"{row['name']:<40} "
                    f"{row['avg_response_time']:<15.2f} "
                    f"{row['p95_response_time']:<15.2f} "
                    f"{error_count:<10}\n"
                )
            
            # Check against thresholds
            f.write("\nThreshold Checks:\n")
            f.write("-" * 80 + "\n")
            
            p95_violations = df[df["p95_response_time"] > 2000]
            if not p95_violations.empty:
                f.write("⚠️  P95 Response Time Violations (>2s):\n")
                for _, row in p95_violations.iterrows():
                    f.write(f"  - {row['name']}: {row['p95_response_time']:.2f}ms\n")
            else:
                f.write("✅ All endpoints meet P95 < 2s requirement\n")
            
            error_rate_violations = df[(df["num_failures"] / df["num_requests"] * 100) > 1]
            if not error_rate_violations.empty:
                f.write("\n⚠️  Error Rate Violations (>1%):\n")
                for _, row in error_rate_violations.iterrows():
                    error_rate = (row["num_failures"] / row["num_requests"] * 100)
                    f.write(f"  - {row['name']}: {error_rate:.2f}%\n")
            else:
                f.write("✅ All endpoints meet error rate < 1% requirement\n")
    
    logger.info(f"Saved summary report to {report_path}")


def compare_reports(baseline_path: Path, current_path: Path, output_path: Path):
    """Compare two load test reports."""
    logger.info(f"Comparing reports: {baseline_path} vs {current_path}")
    
    # Load both reports
    baseline_data = load_locust_json(baseline_path)
    current_data = load_locust_json(current_path)
    
    baseline_metrics, baseline_df = generate_metrics_report(baseline_data, output_path / "baseline")
    current_metrics, current_df = generate_metrics_report(current_data, output_path / "current")
    
    # Generate comparison
    comparison_path = output_path / "comparison.txt"
    
    with open(comparison_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("Load Test Comparison Report\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Baseline: {baseline_path.name}\n")
        f.write(f"Current: {current_path.name}\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n\n")
        
        f.write("Overall Metrics Comparison:\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'Metric':<30} {'Baseline':<20} {'Current':<20} {'Change':<20}\n")
        f.write("-" * 80 + "\n")
        
        # Compare metrics
        metrics_to_compare = [
            ("Total Requests", "total_requests"),
            ("Total Failures", "total_failures"),
            ("RPS", "total_rps"),
            ("Fail Ratio", "fail_ratio"),
        ]
        
        for label, key in metrics_to_compare:
            baseline_val = baseline_metrics.get(key, 0)
            current_val = current_metrics.get(key, 0)
            
            if baseline_val != 0:
                change_pct = ((current_val - baseline_val) / baseline_val) * 100
                change_str = f"{change_pct:+.2f}%"
            else:
                change_str = "N/A"
            
            f.write(
                f"{label:<30} "
                f"{baseline_val:<20} "
                f"{current_val:<20} "
                f"{change_str:<20}\n"
            )
    
    logger.info(f"Saved comparison report to {comparison_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate load test reports")
    parser.add_argument(
        "json_path",
        type=Path,
        help="Path to Locust JSON report"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for reports (default: same as JSON file)"
    )
    parser.add_argument(
        "--compare",
        type=Path,
        help="Path to baseline JSON report for comparison"
    )
    
    args = parser.parse_args()
    
    if not args.json_path.exists():
        logger.error(f"JSON report not found: {args.json_path}")
        return 1
    
    output_dir = args.output_dir or args.json_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load and process report
    locust_data = load_locust_json(args.json_path)
    generate_metrics_report(locust_data, output_dir)
    
    # Compare if baseline provided
    if args.compare:
        if not args.compare.exists():
            logger.error(f"Baseline report not found: {args.compare}")
            return 1
        compare_reports(args.compare, args.json_path, output_dir)
    
    logger.info(f"Reports generated in {output_dir}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
