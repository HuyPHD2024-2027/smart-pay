# MeshPay Benchmark Runner

This directory contains tools for running MeshPay performance benchmarks on Mininet-WiFi mesh networks.

## Quick Start

### Single Benchmark Run

Run a single benchmark with 10 authorities targeting 2000 TPS:

```bash
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --duration 60 --range 10 \
    --output results/bench_10auth_2000tps.csv
```

### Batch Benchmarks

Run all benchmark configurations automatically:

```bash
sudo bash meshpay/examples/run_batch_benchmarks.sh results/batch_$(date +%Y%m%d_%H%M%S)
```

## Available Scripts

### 1. `meshpay_benchmark_runner.py`

Main benchmark script that runs Mininet-WiFi emulations with configurable parameters.

**Key Features:**
- Configurable number of authority nodes
- Target TPS (transactions per second) with automatic client scaling
- Faulty node simulation
- Performance metrics collection
- CSV output compatible with plotting scripts

**Usage:**

```bash
sudo python3 -m meshpay.examples.meshpay_benchmark_runner [OPTIONS]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--authorities N` | Number of authority nodes | 5 |
| `--tps TARGET` | Target transactions per second | 100 |
| `--duration SECONDS` | Benchmark duration | 60 |
| `--range METERS` | Transmission range | 10 |
| `--faulty N` | Number of faulty authorities | 0 |
| `--voting-mode MODE` | Voting mode (weighted/normal) | weighted |
| `--transport PROTO` | Transport protocol (tcp/udp/wifi_direct) | tcp |
| `--output PATH` | Output CSV file path | results/benchmark_result.csv |
| `--loglevel LEVEL` | Mininet log level | info |

**Examples:**

```bash
# Simple benchmark with 5 authorities, 500 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 5 --tps 500 --duration 60

# Benchmark with faulty nodes
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --faulty 3 --tps 150 --duration 60 \
    --output results/10auth_3fault_150tps.csv

# Different transmission range
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --range 20 --duration 60 \
    --output results/10auth_20m_2000tps.csv

# Multiple runs for different configurations
for tps in 500 1000 2000 3000 4000 5000; do
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --tps $tps --duration 60 \
        --output results/10auth_${tps}tps.csv
done
```

### 2. `run_batch_benchmarks.sh`

Automated batch script that runs all benchmark configurations for comprehensive data collection.

**Usage:**

```bash
sudo bash meshpay/examples/run_batch_benchmarks.sh [OUTPUT_DIR]
```

**What it does:**

1. **No-Fault Scenarios:**
   - 5, 10, and 20 authorities
   - TPS: 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000
   - Duration: 60 seconds each

2. **Fault Scenarios:**
   - 5 authorities + 1 faulty
   - 10 authorities + 3 faulty
   - 20 authorities + 6 faulty
   - TPS: 50, 100, 150, 200, 250, 300, 350, 400
   - Duration: 60 seconds each

3. **Range Variation:**
   - 10 authorities at 5m, 10m, 20m ranges
   - TPS: 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000

4. **Combines all results** into a single CSV file

**Example:**

```bash
# Run all benchmarks and save to timestamped directory
sudo bash meshpay/examples/run_batch_benchmarks.sh results/batch_$(date +%Y%m%d_%H%M%S)
```

## Output Format

All benchmarks output CSV files in this format:

```csv
authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s
10,0,weighted,10,1987.50,0.720
```

This format is directly compatible with the plotting scripts in `results/plot_meshpay_comparison.py`.

## Integration with Plotting

After running benchmarks, generate plots:

### Option 1: Use Combined Results

```bash
# Run batch benchmarks
sudo bash meshpay/examples/run_batch_benchmarks.sh results/my_batch

# Copy combined results
cp results/my_batch/meshpay_voting_comparison.csv results/

# Generate plots
python3 results/plot_meshpay_comparison.py
```

### Option 2: Manual Combination

```bash
# Run individual benchmarks
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --output results/data1.csv

sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 20 --tps 3000 --output results/data2.csv

# Combine results
echo "authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s" > results/combined.csv
tail -n +2 -q results/data*.csv >> results/combined.csv

# Generate plots
cp results/combined.csv results/meshpay_voting_comparison.csv
python3 results/plot_meshpay_comparison.py
```

## Understanding the Results

### Console Output

During execution, you'll see:

```
🚀 MeshPay Benchmark Runner
   Authorities: 10
   Target TPS: 2000
   Duration: 60s
   Range: 10m
   Faulty nodes: 0
   Voting mode: weighted
   Calculated clients: 1000 (2.0 tx/s each)
   Transport: tcp

*** Building mesh network
*** Starting authority services
*** Seeding accounts on authorities
*** Starting client services
*** Stabilizing mesh network
*** Using token: 0x1234...
*** Running benchmark for 60s...
*** Benchmark complete

*** Benchmark Results:
   Actual TPS: 1987.50
   Avg Latency: 0.72s
   Success Rate: 98.5%

✓ Results saved to: results/bench_10auth_2000tps.csv
```

### Key Metrics

- **Actual TPS**: Measured transactions per second (may differ from target)
- **Avg Latency**: Average time from transaction initiation to quorum
- **Success Rate**: Percentage of successful transactions

### Client Calculation

The script automatically calculates the number of clients needed:

```
num_clients = max(5, tps // 2)
rate_per_client = tps / num_clients
```

For example:
- Target 100 TPS → 5 clients, 20 tx/s each
- Target 2000 TPS → 1000 clients, 2 tx/s each

## Tips and Best Practices

### 1. System Resources

- Each benchmark requires significant CPU and memory
- Monitor system resources: `htop` or `top`
- Consider reducing duration for testing: `--duration 30`

### 2. Network Stability

- Allow 3-5 seconds for mesh stabilization (built-in)
- Use consistent transmission ranges for comparison
- Avoid running other network-intensive processes

### 3. Batch Execution

- Run batch benchmarks overnight or during low-activity periods
- Expect 1-2 minutes per benchmark (60s run + setup/teardown)
- Total batch run time: ~2-4 hours for all configurations

### 4. Result Validation

- Check if actual TPS matches target (within 10% is acceptable)
- Low success rates may indicate network issues
- Very high latency may indicate overload conditions

## Troubleshooting

### Problem: "Permission denied"

Solution: Run with sudo (Mininet-WiFi requirement)
```bash
sudo python3 -m meshpay.examples.meshpay_benchmark_runner --authorities 10 --tps 2000
```

### Problem: "Module not found"

Solution: Ensure you're in the mininet-wifi directory
```bash
cd /home/huydq/PHD2024-2027/mininet-wifi
sudo python3 -m meshpay.examples.meshpay_benchmark_runner --authorities 10 --tps 2000
```

### Problem: Network doesn't stabilize

Solution: Increase stabilization time or reduce node count
```bash
# The script has 3 seconds built-in, but you can modify if needed
```

### Problem: Low actual TPS compared to target

Possible causes:
- Network overload (reduce target TPS)
- Too many clients (automatic scaling may be too aggressive)
- Transmission range too small (increase `--range`)

## Advanced Usage

### Custom Transport Protocols

```bash
# Use UDP instead of TCP
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --transport udp

# Use WiFi Direct
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --transport wifi_direct
```

### Logging and Debugging

```bash
# Enable debug logging
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --loglevel debug
```

### Modify Batch Script

Edit `run_batch_benchmarks.sh` to customize:
- TPS ranges
- Number of authorities
- Duration per benchmark
- Output directory structure

## See Also

- `fastpay_mesh_benchmark.py` - Original benchmark script with more options
- `meshpay_demo.py` - Interactive mesh demo
- `results/plot_meshpay_comparison.py` - Plotting script for visualizations

