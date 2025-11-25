from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import time
from .packet import Packet

# ============================================================================
# 1. LINK LATENCY & BANDWIDTH TRACKER
# ============================================================================

@dataclass
class LinkMetrics:
    """Metrics for a single link"""
    
    link_id: str
    source_node_id: str
    dest_node_id: str
    latency: float              # ms per packet
    bandwidth: float            # Mbps
    packets_sent: int = 0
    packets_received: int = 0
    total_bytes_transferred: int = 0
    total_transit_time: float = 0.0  # Sum of all packet transit times
    
    def get_avg_transit_time(self) -> float:
        """Average transit time across all packets"""
        if self.packets_received == 0:
            return 0.0
        return self.total_transit_time / self.packets_received
    
    def get_utilization(self) -> float:
        """Theoretical link utilization (0.0 to 1.0+)"""
        if self.packets_sent == 0:
            return 0.0
        # Utilization = (total bytes * 8 bits/byte) / (bandwidth * time)
        # Simplified: just track if bandwidth is being used
        return min(1.0, self.packets_sent / 10.0)  # Normalize to roughly 0-1
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "link_id": self.link_id,
            "source_node_id": self.source_node_id,
            "dest_node_id": self.dest_node_id,
            "latency": self.latency,
            "bandwidth": self.bandwidth,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "total_bytes": self.total_bytes_transferred,
            "avg_transit_time": self.get_avg_transit_time(),
        }


# ============================================================================
# 2. PACKET DELIVERY METRICS
# ============================================================================

@dataclass
class PacketMetrics:
    """Metrics for a single packet's journey"""
    
    packet_id: str
    source_node_id: str
    destination_node_id: str
    path_nodes: List[str]      # Full path
    packet_size: int            # Bytes
    state: str = "queued"       # queued, in_transit, delivered, dropped
    
    # Timing (all in milliseconds since simulation start)
    creation_time: float = 0.0
    sent_time: float = 0.0
    delivery_time: float = 0.0
    
    # Calculated metrics
    path_latencies: List[float] = field(default_factory=list)  # Per-link latencies
    hop_count: int = 0
    total_latency: float = 0.0   # Sum of all link latencies (theoretical)
    actual_latency: float = 0.0  # Actual delivery time - sent time
    bottleneck_bandwidth: float = 0.0  # Minimum bandwidth on path
    throughput: float = 0.0      # Calculated throughput (Mbps)
    
    # Per-link info
    link_ids: List[str] = field(default_factory=list)
    
    def calculate_metrics(self, network_manager) -> None:
        """Calculate all metrics from network state"""
        self.hop_count = len(self.path_nodes) - 1
        
        # Get theoretical latency and bandwidth
        total_lat = 0.0
        min_bw = float('inf')
        
        for i in range(len(self.path_nodes) - 1):
            node_a_id = self.path_nodes[i]
            node_b_id = self.path_nodes[i + 1]
            
            link = network_manager.get_link_by_nodes(node_a_id, node_b_id)
            if link:
                total_lat += link.latency
                min_bw = min(min_bw, link.bandwidth)
                self.path_latencies.append(link.latency)
                self.link_ids.append(link.id)
        
        self.total_latency = total_lat
        if min_bw != float('inf'):
            self.bottleneck_bandwidth = min_bw
        
        # Actual latency is when packet was delivered
        if self.delivery_time > 0 and self.sent_time > 0:
            self.actual_latency = self.delivery_time - self.sent_time
        
        # Throughput = packet size / actual latency
        if self.actual_latency > 0:
            # Convert: (bytes * 8 bits/byte) / (time in ms, convert to seconds)
            throughput_mbps = (self.packet_size * 8) / (self.actual_latency / 1000.0) / 1_000_000
            self.throughput = throughput_mbps
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "packet_id": self.packet_id,
            "source": self.source_node_id,
            "destination": self.destination_node_id,
            "state": self.state,
            "size_bytes": self.packet_size,
            "hops": self.hop_count,
            "theoretical_latency_ms": self.total_latency,
            "actual_latency_ms": self.actual_latency,
            "bottleneck_bandwidth_mbps": self.bottleneck_bandwidth,
            "throughput_mbps": self.throughput,
            "creation_time_ms": self.creation_time,
            "delivery_time_ms": self.delivery_time,
        }


# ============================================================================
# 3. LATENCY & THROUGHPUT ENGINE
# ============================================================================

class LatencyThroughputEngine:
    """
    Central engine for calculating and tracking all latency/throughput metrics
    """
    
    def __init__(self, network_manager, animator_worker):
        """
        Initialize latency engine
        
        Args:
            network_manager: Reference to NetworkManager
            animator_worker: Reference to AnimatorWorker
        """
        self.network_manager = network_manager
        self.animator_worker = animator_worker
        
        self.link_metrics: Dict[str, LinkMetrics] = {}
        self.packet_metrics: Dict[str, PacketMetrics] = {}
        
        self.total_packets_sent = 0
        self.total_packets_delivered = 0
        self.total_packets_dropped = 0
    
    def create_link_metrics(self, link_id: str, source_id: str, dest_id: str,
                          latency: float, bandwidth: float) -> LinkMetrics:
        """
        Create metrics tracker for a link
        
        Args:
            link_id: Link identifier
            source_id: Source node ID
            dest_id: Destination node ID
            latency: Link latency (ms)
            bandwidth: Link bandwidth (Mbps)
        
        Returns:
            LinkMetrics object
        """
        metrics = LinkMetrics(
            link_id=link_id,
            source_node_id=source_id,
            dest_node_id=dest_id,
            latency=latency,
            bandwidth=bandwidth
        )
        self.link_metrics[link_id] = metrics
        return metrics
    
    def create_packet_metrics(self, packet_id: str, source_id: str, dest_id: str,
                            path: List[str], size: int, creation_time: float) -> PacketMetrics:
        """
        Create metrics tracker for a packet
        
        Args:
            packet_id: Packet identifier
            source_id: Source node ID
            dest_id: Destination node ID
            path: Path (list of node IDs)
            size: Packet size (bytes)
            creation_time: When packet was created (simulation time)
        
        Returns:
            PacketMetrics object
        """
        metrics = PacketMetrics(
            packet_id=packet_id,
            source_node_id=source_id,
            destination_node_id=dest_id,
            path_nodes=path,
            packet_size=size,
            creation_time=creation_time,
            sent_time=creation_time,
        )
        
        # Calculate theoretical metrics
        metrics.calculate_metrics(self.network_manager)
        
        self.packet_metrics[packet_id] = metrics
        self.total_packets_sent += 1
        return metrics
    
    def record_packet_sent(self, packet_id: str, sent_time: float) -> None:
        """Record when packet started moving"""
        if packet_id in self.packet_metrics:
            metrics = self.packet_metrics[packet_id]
            metrics.sent_time = sent_time
            metrics.state = "in_transit"
    
    def record_packet_delivery(self, packet_id: str, delivery_time: float) -> None:
        """Record packet delivery"""
        if packet_id in self.packet_metrics:
            metrics = self.packet_metrics[packet_id]
            metrics.delivery_time = delivery_time
            metrics.state = "delivered"
            metrics.calculate_metrics(self.network_manager)
            self.total_packets_delivered += 1
            
            # Update link metrics
            self._update_link_metrics_for_packet(metrics)
    
    def record_packet_drop(self, packet_id: str) -> None:
        """Record packet drop"""
        if packet_id in self.packet_metrics:
            metrics = self.packet_metrics[packet_id]
            metrics.state = "dropped"
            self.total_packets_dropped += 1
    
    def _update_link_metrics_for_packet(self, packet_metrics: PacketMetrics) -> None:
        """Update link metrics when packet is delivered"""
        for link_id in packet_metrics.link_ids:
            if link_id in self.link_metrics:
                link_metric = self.link_metrics[link_id]
                link_metric.packets_sent += 1
                link_metric.packets_received += 1
                link_metric.total_bytes_transferred += packet_metrics.packet_size
                
                # Transit time for this packet
                if packet_metrics.actual_latency > 0:
                    # Rough estimate: divide actual latency by hop count
                    per_link_time = packet_metrics.actual_latency / packet_metrics.hop_count
                    link_metric.total_transit_time += per_link_time
    
    def get_packet_metrics(self, packet_id: str) -> Optional[PacketMetrics]:
        """Get metrics for specific packet"""
        return self.packet_metrics.get(packet_id)
    
    def get_all_metrics(self) -> Dict[str, PacketMetrics]:
        """Get all packet metrics"""
        return self.packet_metrics.copy()
    
    def get_summary_statistics(self) -> dict:
        """Get overall statistics"""
        delivered = self.total_packets_delivered
        dropped = self.total_packets_dropped
        total = delivered + dropped
        
        avg_latency = 0.0
        avg_throughput = 0.0
        max_latency = 0.0
        min_latency = float('inf')
        
        if delivered > 0:
            latencies = []
            throughputs = []
            
            for metrics in self.packet_metrics.values():
                if metrics.state == "delivered":
                    latencies.append(metrics.actual_latency)
                    throughputs.append(metrics.throughput)
                    max_latency = max(max_latency, metrics.actual_latency)
                    min_latency = min(min_latency, metrics.actual_latency)
            
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
            if throughputs:
                avg_throughput = sum(throughputs) / len(throughputs)
        
        if min_latency == float('inf'):
            min_latency = 0.0
        
        return {
            "total_sent": self.total_packets_sent,
            "total_delivered": delivered,
            "total_dropped": dropped,
            "delivery_rate": (delivered / total * 100) if total > 0 else 0,
            "drop_rate": (dropped / total * 100) if total > 0 else 0,
            "avg_latency_ms": avg_latency,
            "min_latency_ms": min_latency,
            "max_latency_ms": max_latency,
            "avg_throughput_mbps": avg_throughput,
        }
    
    def get_link_summary(self) -> List[dict]:
        """Get all link metrics as list of dicts"""
        return [metrics.to_dict() for metrics in self.link_metrics.values()]
    
    def clear_all(self) -> None:
        """Clear all metrics"""
        self.link_metrics.clear()
        self.packet_metrics.clear()
        self.total_packets_sent = 0
        self.total_packets_delivered = 0
        self.total_packets_dropped = 0


# ============================================================================
# 4. ENHANCED PACKET MANAGER (Integration with Latency Engine)
# ============================================================================

class EnhancedPacketManager:
    """
    Extended PacketManager with latency/throughput tracking
    Use this instead of PacketManager from Stage 3
    """
    
    def __init__(self, network_manager, path_manager, animator_worker, 
                 latency_engine: LatencyThroughputEngine):
        """
        Initialize enhanced packet manager
        
        Args:
            network_manager: Reference to NetworkManager
            path_manager: Reference to PathManager
            animator_worker: Reference to AnimatorWorker
            latency_engine: Reference to LatencyThroughputEngine
        """
        self.network_manager = network_manager
        self.path_manager = path_manager
        self.animator_worker = animator_worker
        self.latency_engine = latency_engine
        
        self.all_packets: List = []
        self.active_packets: Dict[str, 'Packet'] = {}
        self.delivered_packets: List = []
        self.dropped_packets: List = []
        self.packet_counter = 0
    
    def create_packet(self, source_id: str, dest_id: str, size: int = 1024):
        """
        Create a new packet with metrics tracking
        
        Args:
            source_id: Source node ID
            dest_id: Destination node ID
            size: Packet size (bytes)
        
        Returns:
            Packet object, or None if invalid
        """
        # Validate nodes
        if source_id not in self.network_manager.nodes or \
           dest_id not in self.network_manager.nodes:
            return None
        
        if source_id == dest_id:
            return None
        
        self.packet_counter += 1
        packet_id = f"PKT{self.packet_counter:04d}"
        current_time = self.animator_worker.sim_time
        
        # Get path
        if not self.path_manager.set_path(source_id, dest_id):
            return None
        
        path_nodes = self.path_manager.get_current_path_nodes()
        
        # Import Packet class from packet module
        from packet import Packet, PacketState
        
        packet = Packet(
            id=packet_id,
            source_node_id=source_id,
            destination_node_id=dest_id,
            creation_time=current_time,
            sent_time=current_time,
            size=size,
            path=path_nodes,
            state=PacketState.QUEUED
        )
        
        packet.current_node_id = source_id
        
        self.all_packets.append(packet)
        self.active_packets[packet_id] = packet
        
        # Create metrics for this packet
        self.latency_engine.create_packet_metrics(
            packet_id, source_id, dest_id, path_nodes, size, current_time
        )
        
        return packet
    
    def start_packet_animation(self, packet) -> bool:
        """
        Start animating a packet on first link
        
        Args:
            packet: Packet to animate
        
        Returns:
            True if animation started, False otherwise
        """
        if len(packet.path) < 2:
            packet.mark_dropped()
            self.latency_engine.record_packet_drop(packet.id)
            return False
        
        # Get first link
        node_a_id = packet.path[0]
        node_b_id = packet.path[1]
        
        link = self.network_manager.get_link_by_nodes(node_a_id, node_b_id)
        if not link:
            packet.mark_dropped()
            self.latency_engine.record_packet_drop(packet.id)
            return False
        
        node_a = self.network_manager.nodes[node_a_id]
        node_b = self.network_manager.nodes[node_b_id]
        
        from packet import PacketState
        packet.state = PacketState.IN_TRANSIT
        packet.current_link_index = 0
        packet.link_latency = link.latency
        
        # Record sent time
        self.latency_engine.record_packet_sent(packet.id, self.animator_worker.sim_time)
        
        # Add to animator
        self.animator_worker.add_packet(
            packet,
            (node_a.x, node_a.y),
            (node_b.x, node_b.y),
            link.latency
        )
        
        return True
    
    def advance_packet(self, packet) -> bool:
        """
        Move packet to next link in path
        
        Args:
            packet: Packet to advance
        
        Returns:
            True if packet reached destination, False otherwise
        """
        current_time = self.animator_worker.sim_time
        from packet import PacketState
        
        if packet.move_to_next_link(current_time):
            # Reached destination
            packet.mark_delivered(current_time)
            self.latency_engine.record_packet_delivery(packet.id, current_time)
            self.delivered_packets.append(packet)
            if packet.id in self.active_packets:
                del self.active_packets[packet.id]
            return True
        
        # Start animation on next link
        if packet.path_index + 1 < len(packet.path):
            node_a_id = packet.path[packet.path_index]
            node_b_id = packet.path[packet.path_index + 1]
            
            link = self.network_manager.get_link_by_nodes(node_a_id, node_b_id)
            if link:
                node_a = self.network_manager.nodes[node_a_id]
                node_b = self.network_manager.nodes[node_b_id]
                
                packet.link_latency = link.latency
                
                self.animator_worker.add_packet(
                    packet,
                    (node_a.x, node_a.y),
                    (node_b.x, node_b.y),
                    link.latency
                )
        
        return False
    
    def drop_packet(self, packet) -> None:
        """Mark packet as dropped"""
        packet.mark_dropped()
        self.latency_engine.record_packet_drop(packet.id)
        self.dropped_packets.append(packet)
        if packet.id in self.active_packets:
            del self.active_packets[packet.id]
        self.animator_worker.remove_packet(packet.id)
    
    def get_statistics(self) -> dict:
        """Get packet statistics"""
        return self.latency_engine.get_summary_statistics()
    
    def clear_all(self) -> None:
        """Clear all packets and metrics"""
        self.all_packets.clear()
        self.active_packets.clear()
        self.delivered_packets.clear()
        self.dropped_packets.clear()
        self.packet_counter = 0
        self.latency_engine.clear_all()


# ============================================================================
# 5. METRICS DISPLAY WIDGET (Enhanced for Stage 4)
# ============================================================================

class EnhancedMetricsDisplay:
    """
    Enhanced display for latency/throughput metrics
    """
    
    def __init__(self, label_widget, latency_engine: LatencyThroughputEngine):
        """
        Initialize metrics display
        
        Args:
            label_widget: Tkinter Label widget
            latency_engine: Reference to LatencyThroughputEngine
        """
        self.label = label_widget
        self.latency_engine = latency_engine
        self.current_packet_metrics = None
    
    def update_display(self) -> None:
        """Refresh metrics display with current statistics"""
        stats = self.latency_engine.get_summary_statistics()
        
        display_text = (
            f"═══════════════════════════════════════════════════════════\n"
            f"📊 NETWORK PERFORMANCE METRICS\n"
            f"═══════════════════════════════════════════════════════════\n"
            f"\n"
            f"📈 PACKET STATISTICS\n"
            f"  Sent:        {stats['total_sent']} packets\n"
            f"  Delivered:   {stats['total_delivered']} packets\n"
            f"  Dropped:     {stats['total_dropped']} packets\n"
            f"  Success Rate: {stats['delivery_rate']:.1f}%\n"
            f"\n"
            f"⏱️  LATENCY METRICS\n"
            f"  Average:     {stats['avg_latency_ms']:.2f} ms\n"
            f"  Minimum:     {stats['min_latency_ms']:.2f} ms\n"
            f"  Maximum:     {stats['max_latency_ms']:.2f} ms\n"
            f"\n"
            f"🚀 THROUGHPUT METRICS\n"
            f"  Average:     {stats['avg_throughput_mbps']:.2f} Mbps\n"
            f"\n"
            f"═══════════════════════════════════════════════════════════"
        )
        
        self.label.config(text=display_text)
    
    def update_packet_detail(self, packet_id: str) -> None:
        """Update display with specific packet metrics"""
        metrics = self.latency_engine.get_packet_metrics(packet_id)
        
        if not metrics:
            self.label.config(text="Packet not found")
            return
        
        display_text = (
            f"═══════════════════════════════════════════════════════════\n"
            f"📦 PACKET DETAILS: {packet_id}\n"
            f"═══════════════════════════════════════════════════════════\n"
            f"\n"
            f"Source → Destination:  {metrics.source_node_id} → {metrics.destination_node_id}\n"
            f"Path:                  {' → '.join(metrics.path_nodes)}\n"
            f"Hops:                  {metrics.hop_count}\n"
            f"Size:                  {metrics.packet_size} bytes\n"
            f"State:                 {metrics.state}\n"
            f"\n"
            f"⏱️  TIMING\n"
            f"  Theoretical Latency: {metrics.total_latency:.2f} ms\n"
            f"  Actual Latency:      {metrics.actual_latency:.2f} ms\n"
            f"  Delay Factor:        {metrics.actual_latency/metrics.total_latency:.2f}x\n"
            f"\n"
            f"💾 BANDWIDTH\n"
            f"  Bottleneck:          {metrics.bottleneck_bandwidth:.1f} Mbps\n"
            f"  Achieved Throughput: {metrics.throughput:.2f} Mbps\n"
            f"\n"
            f"═══════════════════════════════════════════════════════════"
        )
        
        self.label.config(text=display_text)

