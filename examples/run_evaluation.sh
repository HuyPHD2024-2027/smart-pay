#!/bin/bash

# FastPay Mesh Network Evaluation Runner
# This script runs all evaluation experiments and generates results

set -e

echo "=========================================="
echo "FastPay Mesh Network Evaluation"
echo "=========================================="

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Create results directory
RESULTS_DIR="evaluation_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo "Results will be saved to: $RESULTS_DIR"

# Function to run experiment with error handling
run_experiment() {
    local experiment_name=$1
    local output_file="$RESULTS_DIR/${experiment_name}_results.json"
    
    echo ""
    echo "Running $experiment_name experiment..."
    echo "Output: $output_file"
    
    if python3 fastpay_evaluation.py --experiment "$experiment_name" --output "$output_file"; then
        echo "✓ $experiment_name completed successfully"
    else
        echo "✗ $experiment_name failed"
        return 1
    fi
}

# Run all experiments
echo ""
echo "Starting evaluation experiments..."

# 1. Baseline experiment (50 authorities, 200 users)
run_experiment "baseline"

# 2. Scaling experiments (20-80 authorities)
run_experiment "scaling"

# 3. Mobility robustness test
run_experiment "mobility"

# 4. WiFi Direct comparison
run_experiment "wifi_direct"

# Generate summary report
echo ""
echo "Generating summary report..."

python3 -c "
import json
import glob
import os

results_dir = '$RESULTS_DIR'
result_files = glob.glob(os.path.join(results_dir, '*_results.json'))

print('\\n' + '='*80)
print('FASTPAY MESH EVALUATION SUMMARY')
print('='*80)

all_results = []
for file in result_files:
    with open(file, 'r') as f:
        data = json.load(f)
        if isinstance(data, list):
            all_results.extend(data)
        else:
            all_results.append(data)

# Sort by experiment name
all_results.sort(key=lambda x: x.get('experiment_name', ''))

for result in all_results:
    name = result.get('experiment_name', 'unknown')
    authorities = result.get('num_authorities', 0)
    users = result.get('num_users', 0)
    median_latency = result.get('median_latency_ms', 0)
    p95_latency = result.get('p95_latency_ms', 0)
    success_rate = result.get('success_rate', 0)
    total_tx = result.get('total_transactions', 0)
    
    print(f'\\n{name.upper()}:')
    print(f'  Authorities: {authorities}, Users: {users}')
    print(f'  Median Latency: {median_latency:.1f}ms')
    print(f'  95th Percentile: {p95_latency:.1f}ms')
    print(f'  Success Rate: {success_rate:.1%}')
    print(f'  Total Transactions: {total_tx}')

print('\\n' + '='*80)
print('Evaluation completed successfully!')
print(f'All results saved in: {results_dir}')
print('='*80)
"

echo ""
echo "Evaluation completed!"
echo "Results directory: $RESULTS_DIR"
echo ""
echo "To view detailed results:"
echo "  cat $RESULTS_DIR/*_results.json | jq ."
echo ""
echo "To regenerate summary:"
echo "  python3 -c \"import json; import glob; [print(json.dumps(json.load(open(f)), indent=2)) for f in glob.glob('$RESULTS_DIR/*_results.json')]\"" 