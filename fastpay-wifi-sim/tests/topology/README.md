# FastPay WiFi Authority System Tests

This directory contains tests for FastPay authority nodes in a WiFi network environment using mininet-wifi.

## Overview

The `test_authority_mobility.py` file creates a network topology with multiple WiFiAuthority nodes to test Byzantine Fault Tolerance (BFT) consensus, transfer order processing, signature verification, and other core authority functionality in a realistic wireless environment.

## Features

- **4 WiFi Authority Nodes**: Creates a committee of 4 authorities for BFT testing
- **Comprehensive Authority Testing**: Tests all major authority functions
- **BFT Consensus Testing**: Tests 2/3 quorum requirements
- **Transfer Order Validation**: Tests signature verification and balance checks
- **Insufficient Balance Handling**: Tests rejection of invalid transfers
- **Confirmation Order Processing**: Tests multi-signature confirmation orders
- **Real Mininet-WiFi Integration**: Uses actual wireless network simulation

## Usage

### Basic Test (Automated)
```bash
sudo PYTHONPATH=. python tests/topology/test_authority_mobility.py
```

### Interactive Mode (with CLI)
```bash
sudo PYTHONPATH=. python tests/topology/test_authority_mobility.py -i
```

### Without Plotting (for headless servers)
```bash
sudo PYTHONPATH=. python tests/topology/test_authority_mobility.py -p
```

### Combined Options
```bash
sudo PYTHONPATH=. python tests/topology/test_authority_mobility.py -i -p
```

## Command Line Options

- `-i`: Enter interactive CLI mode after tests
- `-p`: Skip network plotting (useful for headless environments)

## Test Scenarios

### 1. Authority Initialization Test
- Verifies all authorities are properly initialized
- Checks accounts, committee members, public keys, and peer connections

### 2. Balance Management Test
- Tests balance queries across all authorities
- Verifies consistency of account balances

### 3. Signature Verification Test
- Tests valid signature verification
- Tests rejection of invalid signatures
- Tests rejection with wrong public keys

### 4. Transfer Order Validation Test
- Tests validation of legitimate transfer orders
- Tests rejection of negative amounts
- Tests rejection of same sender/recipient transfers

### 5. BFT Consensus Test
- Creates a transfer order from user1 to user2 (100 units)
- Tests if the 4-authority committee can achieve 2/3 consensus (3 out of 4)
- Verifies signature validation and balance updates

### 6. Insufficient Balance Test
- Tests rejection of transfers exceeding account balance
- Verifies all authorities consistently reject invalid transfers

### 7. Confirmation Order Test
- Tests multi-signature confirmation order processing
- Verifies 2/3 quorum requirement for confirmation orders

## Network Topology

```
    auth1 (30,30) ---- auth2 (60,30)
        |                   |
        |                   |
    auth3 (30,60) ---- auth4 (60,60)
                \      /
                 \    /
                  ap1 (45,45)
                   |
                  h1 (host)
```

## Test Accounts

The system initializes with these test accounts:
- user1: 1000 units
- user2: 800 units  
- user3: 1200 units
- user4: 500 units
- user5: 2000 units

## Interactive Commands

When running with `-i` flag, you can use mininet-wifi CLI commands:

```bash
# Check authority connectivity
mininet-wifi> pingall

# Check authority status
mininet-wifi> py print(test.authorities[0].name)
mininet-wifi> py print(test.authorities[0].get_account_balance('user1'))

# Check network links
mininet-wifi> links

# Inspect authority performance
mininet-wifi> py print(test.authorities[0].get_performance_stats())

# Exit
mininet-wifi> exit
```

## Requirements

- Root privileges (sudo) for mininet-wifi
- Python 3.8+
- mininet-wifi installed
- matplotlib (for plotting)
- FastPay core modules

## Expected Output

```
*** Creating FastPay WiFi Network
*** Creating nodes
*** Configuring propagation model
*** Configuring nodes
*** Creating links
*** Starting network
*** Initializing FastPay authorities
*** Initialized 4 FastPay authorities
*** Running FastPay Authority System Tests
*** Testing authority initialization
Authority auth1: OK
Authority auth2: OK
Authority auth3: OK
Authority auth4: OK
*** Authority Initialization: PASSED
*** Testing balance management
User user1 balance consistency: OK (balances: [1000, 1000, 1000, 1000])
User user2 balance consistency: OK (balances: [800, 800, 800, 800])
User user3 balance consistency: OK (balances: [1200, 1200, 1200, 1200])
User user4 balance consistency: OK (balances: [500, 500, 500, 500])
User user5 balance consistency: OK (balances: [2000, 2000, 2000, 2000])
*** Balance Management: PASSED
*** Testing signature verification
Valid signature verification: OK
Invalid signature rejection: OK
Wrong public key rejection: OK
*** Signature Verification: PASSED
*** Testing transfer order validation
Valid transfer order: OK
Negative amount rejection: OK
Same sender/recipient rejection: OK
*** Transfer Order Validation: PASSED
*** Testing BFT consensus (2/3 quorum)
*** Processing transfer order: <uuid>
Authority auth1: SUCCESS - New balance: 900
Authority auth2: SUCCESS - New balance: 900
Authority auth3: SUCCESS - New balance: 900
Authority auth4: SUCCESS - New balance: 900
*** Consensus result: 4/4 authorities approved
*** Required: 3, Achieved: YES
*** Testing insufficient balance handling
Authority auth1: REJECTED - Insufficient balance for transfer
Authority auth2: REJECTED - Insufficient balance for transfer
Authority auth3: REJECTED - Insufficient balance for transfer
Authority auth4: REJECTED - Insufficient balance for transfer
*** Insufficient Balance Test: PASSED
*** Testing confirmation order processing
Authority auth1: CONFIRMED
Authority auth2: CONFIRMED
Authority auth3: CONFIRMED
Authority auth4: CONFIRMED
*** Confirmation Orders: PASSED
    - Quorum achieved: YES (3/3)
    - All confirmed: YES
*** Test Results Summary
Initialization: PASSED
Balance Management: PASSED
Signature Verification: PASSED
Transfer Validation: PASSED
Bft Consensus: PASSED
Insufficient Balance: PASSED
Confirmation Orders: PASSED
*** Overall: 7/7 tests passed
*** Stopping network
```

## Troubleshooting

1. **Permission Denied**: Run with `sudo`
2. **Module Not Found**: Ensure you're in the fastpay-wifi-sim directory
3. **Matplotlib Issues**: Install with `pip install matplotlib`
4. **Network Issues**: Check if mininet-wifi is properly installed
5. **Authority Errors**: Check that core.authority module is properly implemented

## Integration with Regular Tests

You can also run this as part of the pytest suite:

```bash
# From fastpay-wifi-sim directory
sudo python -m pytest tests/topology/ -v
```

## Extending the Tests

To add new authority tests, create new methods in the `FastPayAuthorityTest` class:

```python
def test_new_functionality(self):
    """Test new authority functionality."""
    info("*** Testing new functionality\n")
    
    # Your test logic here
    test_passed = True  # Your test logic
    
    info(f"*** New Functionality: {'PASSED' if test_passed else 'FAILED'}\n")
    return test_passed
```

Then add it to the `run_all_tests` method to include it in the test suite. 