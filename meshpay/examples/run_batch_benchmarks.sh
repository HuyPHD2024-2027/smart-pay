#!/bin/bash
#
# Batch benchmark runner for MeshPay performance experiments
# This script runs multiple configurations to collect data for plotting
#
# Usage:
#   sudo bash run_batch_benchmarks.sh [output_dir]
#
# Example:
#   sudo bash run_batch_benchmarks.sh results/batch_$(date +%Y%m%d_%H%M%S)

set -e

# Default output directory
OUTPUT_DIR="${1:-results/batch_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUTPUT_DIR"

echo "========================================="
echo "MeshPay Batch Benchmark Runner"
echo "Output directory: $OUTPUT_DIR"
echo "========================================="

# Configuration
DURATION=60  # seconds per benchmark
RANGE=10     # transmission range in meters

echo ""
echo "=== Running No-Fault Scenarios ==="
echo ""

# 5 authorities, no faults
for tps in 500 1000 1500 2000 2500 3000 3500 4000 4500 5000; do
    echo "Running: 5 authorities, 0 faults, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 5 --faulty 0 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/5auth_0fault_${tps}tps.csv" || echo "  Failed!"
done

# 10 authorities, no faults
for tps in 500 1000 1500 2000 2500 3000 3500 4000 4500 5000; do
    echo "Running: 10 authorities, 0 faults, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --faulty 0 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/10auth_0fault_${tps}tps.csv" || echo "  Failed!"
done

# 20 authorities, no faults
for tps in 500 1000 1500 2000 2500 3000 3500 4000 4500 5000; do
    echo "Running: 20 authorities, 0 faults, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 20 --faulty 0 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/20auth_0fault_${tps}tps.csv" || echo "  Failed!"
done

echo ""
echo "=== Running Fault Scenarios ==="
echo ""

# 5 authorities, 1 faulty
for tps in 50 100 150 200 250 300 350 400; do
    echo "Running: 5 authorities, 1 faulty, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 5 --faulty 1 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/5auth_1fault_${tps}tps.csv" || echo "  Failed!"
done

# 10 authorities, 3 faulty
for tps in 50 100 150 200 250 300 350 400; do
    echo "Running: 10 authorities, 3 faulty, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --faulty 3 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/10auth_3fault_${tps}tps.csv" || echo "  Failed!"
done

# 20 authorities, 6 faulty
for tps in 50 100 150 200 250 300 350 400; do
    echo "Running: 20 authorities, 6 faulty, ${tps} TPS..."
    python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 20 --faulty 6 --tps $tps \
        --duration $DURATION --range $RANGE \
        --output "${OUTPUT_DIR}/20auth_6fault_${tps}tps.csv" || echo "  Failed!"
done

echo ""
echo "=== Running Range Variation Scenarios ==="
echo ""

# 10 authorities at different ranges
for range in 5 10 20; do
    for tps in 500 1000 1500 2000 2500 3000 3500 4000 4500 5000; do
        echo "Running: 10 authorities, 0 faults, ${range}m range, ${tps} TPS..."
        python3 -m meshpay.examples.meshpay_benchmark_runner \
            --authorities 10 --faulty 0 --tps $tps \
            --duration $DURATION --range $range \
            --output "${OUTPUT_DIR}/10auth_0fault_${range}m_${tps}tps.csv" || echo "  Failed!"
    done
done

echo ""
echo "=== Combining Results ==="
echo ""

# Combine all results into a single CSV
COMBINED_FILE="${OUTPUT_DIR}/meshpay_voting_comparison.csv"
echo "authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s" > "$COMBINED_FILE"

# Append all result files (skip headers)
for file in "${OUTPUT_DIR}"/*.csv; do
    if [[ "$file" != "$COMBINED_FILE" ]]; then
        tail -n +2 "$file" >> "$COMBINED_FILE" || true
    fi
done

echo "Combined results saved to: $COMBINED_FILE"
echo ""
echo "========================================="
echo "Batch benchmarks complete!"
echo "Total result files: $(ls -1 "${OUTPUT_DIR}"/*.csv | wc -l)"
echo "========================================="
echo ""
echo "To generate plots, run:"
echo "  cp $COMBINED_FILE results/meshpay_voting_comparison.csv"
echo "  python3 results/plot_meshpay_comparison.py"

