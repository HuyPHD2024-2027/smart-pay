"""Performance metrics collection module for FastPay simulation."""

import time
from typing import Any, Dict

from .base_types import NetworkMetrics


class MetricsCollector:
    """Performance metrics collector for authority node."""
    
    def __init__(self) -> None:
        """Initialize metrics collector."""
        self.network_metrics = NetworkMetrics(
            latency=0.0,
            bandwidth=0.0,
            packet_loss=0.0,
            connectivity_ratio=0.0,
            last_update=time.time()
        )
        self.transaction_count = 0
        self.error_count = 0
        self.sync_count = 0
        
    def record_transaction(self) -> None:
        """Record a transaction."""
        self.transaction_count += 1
        
    def record_error(self) -> None:
        """Record an error."""
        self.error_count += 1
        
    def record_sync(self) -> None:
        """Record a synchronization."""
        self.sync_count += 1
        
    def update_network_metrics(self, metrics: NetworkMetrics) -> None:
        """Update network metrics.
        
        Args:
            metrics: New network metrics
        """
        self.network_metrics = metrics
        
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics.
        
        Returns:
            Dictionary containing performance stats
        """
        return {
            'transaction_count': self.transaction_count,
            'error_count': self.error_count,
            'sync_count': self.sync_count,
            'network_metrics': {
                'latency': self.network_metrics.latency,
                'bandwidth': self.network_metrics.bandwidth,
                'packet_loss': self.network_metrics.packet_loss,
                'connectivity_ratio': self.network_metrics.connectivity_ratio,
            }
        } 