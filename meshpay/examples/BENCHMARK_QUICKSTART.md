# MeshPay Benchmark Quick Reference

## Single Run Examples

### Basic Usage
```bash
# Run benchmark with 10 authorities, targeting 2000 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --duration 60 --range 10 \
    --output results/my_benchmark.csv
```

### No-Fault Scenarios
```bash
# 5 authorities, 1000 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 5 --tps 1000 --output results/5auth_1000tps.csv

# 10 authorities, 2000 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --output results/10auth_2000tps.csv

# 20 authorities, 3000 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 20 --tps 3000 --output results/20auth_3000tps.csv
```

### Fault Scenarios
```bash
# 5 authorities, 1 faulty, 100 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 5 --faulty 1 --tps 100 --output results/5auth_1fault_100tps.csv

# 10 authorities, 3 faulty, 200 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --faulty 3 --tps 200 --output results/10auth_3fault_200tps.csv

# 20 authorities, 6 faulty, 300 TPS
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 20 --faulty 6 --tps 300 --output results/20auth_6fault_300tps.csv
```

### Range Variation
```bash
# 10 authorities at 5m range
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --range 5 --output results/10auth_5m_2000tps.csv

# 10 authorities at 20m range
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 2000 --range 20 --output results/10auth_20m_2000tps.csv
```

## Batch Runs

### Full Batch (All Configurations)
```bash
sudo bash meshpay/examples/run_batch_benchmarks.sh results/batch_$(date +%Y%m%d_%H%M%S)
```

### Manual Loop - No Faults
```bash
# Test different TPS for 10 authorities
for tps in 500 1000 1500 2000 2500 3000 3500 4000 4500 5000; do
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --tps $tps --duration 60 \
        --output results/10auth_${tps}tps.csv
done
```

### Manual Loop - With Faults
```bash
# Test different TPS for 10 authorities with 3 faults
for tps in 50 100 150 200 250 300 350 400; do
    sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
        --authorities 10 --faulty 3 --tps $tps --duration 60 \
        --output results/10auth_3fault_${tps}tps.csv
done
```

## Combine Results and Plot

```bash
# Combine all CSV results
echo "authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s" > results/meshpay_voting_comparison.csv
tail -n +2 -q results/*auth*.csv >> results/meshpay_voting_comparison.csv

# Generate plots
python3 results/plot_meshpay_comparison.py
```

## Quick Parameter Reference

| Parameter | Description | Example Values |
|-----------|-------------|----------------|
| `--authorities` | Number of authority nodes | 5, 10, 20 |
| `--tps` | Target transactions/second | 100, 500, 1000, 2000 |
| `--duration` | Benchmark duration (seconds) | 30, 60, 120 |
| `--range` | Transmission range (meters) | 5, 10, 20, 50 |
| `--faulty` | Number of faulty authorities | 0, 1, 3, 6 |
| `--voting-mode` | Voting algorithm | weighted, normal |
| `--transport` | Network protocol | tcp, udp, wifi_direct |
| `--output` | Output CSV file path | results/benchmark.csv |

## Expected Output Format

```csv
authorities,faulty_nodes,voting_type,transmission_range_m,throughput_tps,avg_latency_s
10,0,weighted,10,1987.50,0.720
```

## Typical Run Times

- Single benchmark: ~1-2 minutes (60s run + setup/teardown)
- No-fault batch (30 runs): ~45-60 minutes
- Fault batch (24 runs): ~35-50 minutes
- Full batch (all scenarios): ~2-4 hours

## Common Issues

### "Permission denied"
```bash
# Always use sudo
sudo python3 -m meshpay.examples.meshpay_benchmark_runner ...
```

### "Module not found"
```bash
# Make sure you're in the right directory
cd /home/huydq/PHD2024-2027/mininet-wifi
sudo python3 -m meshpay.examples.meshpay_benchmark_runner ...
```

### Low throughput
```bash
# Reduce target TPS or increase range
sudo python3 -m meshpay.examples.meshpay_benchmark_runner \
    --authorities 10 --tps 1000 --range 20  # Increased range
```

## Next Steps

1. Run a test benchmark to verify setup
2. Run batch benchmarks for data collection  
3. Combine results and generate plots
4. Analyze performance characteristics

For detailed documentation, see `README_BENCHMARK.md`

