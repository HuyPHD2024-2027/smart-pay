"""
Authority logging functionality for FastPay WiFi CLI testing.

This module provides the AuthorityLogger class for displaying authority
activity in separate xterm terminals with color-coded console output.
"""

import time
import queue
import subprocess
import os
from typing import Optional


class AuthorityLogger:
    """Logger for authority message processing with terminal output."""
    
    def __init__(self, authority_name: str, log_file: Optional[str] = None) -> None:
        """Initialize the authority logger.
        
        Args:
            authority_name: Name of the authority
            log_file: Optional log file path (defaults to /tmp/{authority_name}_log.txt)
        """
        self.authority_name = authority_name
        self.log_file = log_file or f"/tmp/{authority_name}_log.txt"
        self.log_queue = queue.Queue()
        self.running = True
        self.terminal_process: Optional[subprocess.Popen] = None
        
        # Color mapping for different authorities
        self.colors = {
            'auth1': '\033[94m',    # Blue
            'auth2': '\033[92m',    # Green  
            'auth3': '\033[93m',    # Yellow
            'auth4': '\033[95m',    # Magenta
            'auth5': '\033[96m',    # Cyan
            'auth6': '\033[91m',    # Red
        }
        self.reset_color = '\033[0m'
        
    def start_terminal(self) -> None:
        """Start a separate xterm terminal for this authority's logs."""
        # Create log file
        try:
            with open(self.log_file, 'w') as f:
                f.write(f"=== {self.authority_name} Authority Log ===\n")
                f.write(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("="*50 + "\n\n")
        except IOError as e:
            print(f"Warning: Could not create log file {self.log_file}: {e}")
            return
        
        # Start xterm terminal that tails the log file
        cmd = f"xterm -T '{self.authority_name} Authority Log' -geometry 80x30 -e 'tail -f {self.log_file}' &"
        try:
            self.terminal_process = subprocess.Popen(cmd, shell=True)
            print(f"📋 {self.authority_name} terminal opened - logging to: {self.log_file}")
        except Exception as e:
            print(f"Could not open xterm for {self.authority_name}: {e}")
            print(f"Log file available at: {self.log_file}")
            print(f"💡 You can monitor logs with: tail -f {self.log_file}")
    
    def log(self, message: str) -> None:
        """Log a message with timestamp.
        
        Args:
            message: Message to log
        """
        timestamp = time.strftime('%H:%M:%S.%f')[:-3]
        log_entry = f"[{timestamp}] {self.authority_name}: {message}"
        
        # Write to file
        try:
            with open(self.log_file, 'a') as f:
                f.write(log_entry + "\n")
                f.flush()  # Force write to disk
        except IOError:
            # If file writing fails, continue with console output
            pass
        
        # Also print to console with authority color coding
        color = self.colors.get(self.authority_name, '')
        print(f"{color}{log_entry}{self.reset_color}")
    
    def error(self, message: str) -> None:
        """Log an error message.
        
        Args:
            message: Error message to log
        """
        self.log(f"❌ ERROR: {message}")
    
    def info(self, message: str) -> None:
        """Log an info message.
        
        Args:
            message: Info message to log
        """
        self.log(f"ℹ️  INFO: {message}")
    
    def warning(self, message: str) -> None:
        """Log a warning message.
        
        Args:
            message: Warning message to log
        """
        self.log(f"⚠️  WARNING: {message}")
    
    def debug(self, message: str) -> None:
        """Log a debug message.
        
        Args:
            message: Debug message to log
        """
        self.log(f"🐛 DEBUG: {message}")
    
    def success(self, message: str) -> None:
        """Log a success message.
        
        Args:
            message: Success message to log
        """
        self.log(f"✅ SUCCESS: {message}")
    
    def processing(self, message: str) -> None:
        """Log a processing message.
        
        Args:
            message: Processing message to log
        """
        self.log(f"⚙️  PROCESSING: {message}")
    
    def received(self, message: str) -> None:
        """Log a received message.
        
        Args:
            message: Received message to log
        """
        self.log(f"📨 RECEIVED: {message}")
    
    def sent(self, message: str) -> None:
        """Log a sent message.
        
        Args:
            message: Sent message to log
        """
        self.log(f"📤 SENT: {message}")
    
    def validation(self, message: str) -> None:
        """Log a validation message.
        
        Args:
            message: Validation message to log
        """
        self.log(f"🔍 VALIDATION: {message}")
    
    def balance(self, message: str) -> None:
        """Log a balance-related message.
        
        Args:
            message: Balance message to log
        """
        self.log(f"💰 BALANCE: {message}")
    
    def transfer(self, message: str) -> None:
        """Log a transfer-related message.
        
        Args:
            message: Transfer message to log
        """
        self.log(f"🔄 TRANSFER: {message}")
    
    def ping(self, message: str) -> None:
        """Log a ping-related message.
        
        Args:
            message: Ping message to log
        """
        self.log(f"🏓 PING: {message}")
    
    def shutdown(self, message: str) -> None:
        """Log a shutdown message.
        
        Args:
            message: Shutdown message to log
        """
        self.log(f"🔄 SHUTDOWN: {message}")
    
    def close(self) -> None:
        """Close the logger and terminal."""
        self.running = False
        if self.terminal_process:
            try:
                self.terminal_process.terminate()
            except Exception:
                # Process might already be terminated
                pass
    
    def __enter__(self):
        """Context manager entry."""
        self.start_terminal()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close() 