from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Deque
from collections import deque
from enum import Enum
import time
from packet import Packet

# ============================================================================
# 1. QUEUE DISCIPLINE
# ============================================================================

class DropPolicy(Enum):
    """Queue drop policies"""
    TAIL_DROP = "tail_drop"          # Drop newest packet
    HEAD_DROP = "head_drop"          # Drop oldest packet
    RANDOM_DROP = "random_drop"      # Drop random packet


@dataclass
class LinkQueue:
    """
    Queue buffer for a network link
    Simulates packet buffering and dropping
    """
    
    link_id: str
    capacity: int                    # Max packets in queue
    drop_policy: DropPolicy = DropPolicy.TAIL_DROP
    queue: Deque = field(default_factory=deque)
    
    packets_enqueued: int = 0        # Total packets attempted
    packets_dequeued: int = 0        # Total packets successfully sent
    packets_dropped: int = 0         # Total packets dropped
    total_queue_delay: float = 0.0   # Sum of all queuing delays
    
    def enqueue(self, packet, current_time: float) -> bool:
        """
        Add packet to queue
        
        Args:
            packet: Packet object
            current_time: Current simulation time (ms)
        
        Returns:
            True if accepted, False if dropped
        """
        self.packets_enqueued += 1
        
        # Queue has space
        if len(self.queue) < self.capacity:
            self.queue.append({
                'packet': packet,
                'enqueue_time': current_time
            })
            return True
        
        # Queue is full - apply drop policy
        self.packets_dropped += 1
        
        if self.drop_policy == DropPolicy.TAIL_DROP:
            # Drop newest (don't add it)
            return False
        
        elif self.drop_policy == DropPolicy.HEAD_DROP:
            # Drop oldest from queue
            if self.queue:
                self.queue.popleft()
                self.queue.append({
                    'packet': packet,
                    'enqueue_time': current_time
                })
            return True
        
        elif self.drop_policy == DropPolicy.RANDOM_DROP:
            # Drop random from queue
            import random
            if self.queue:
                idx = random.randint(0, len(self.queue) - 1)
                queue_list = list(self.queue)
                queue_list.pop(idx)
                self.queue = deque(queue_list)
                self.queue.append({
                    'packet': packet,
                    'enqueue_time': current_time
                })
            return True
        
        return False
    
    def dequeue(self, current_time: float) -> Optional[Tuple]:
        """
        Remove packet from front of queue
        
        Args:
            current_time: Current simulation time (ms)
        
        Returns:
            Tuple (packet, queuing_delay_ms) or None if empty
        """
        if not self.queue:
            return None
        
        item = self.queue.popleft()
        packet = item['packet']
        enqueue_time = item['enqueue_time']
        
        # Calculate queuing delay
        queuing_delay = current_time - enqueue_time
        self.total_queue_delay += queuing_delay
        self.packets_dequeued += 1
        
        return (packet, queuing_delay)
    
    def get_size(self) -> int:
        """Current queue size"""
        return len(self.queue)
    
    def get_utilization(self) -> float:
        """Queue utilization (0.0 to 1.0)"""
        if self.capacity == 0:
            return 0.0
        return len(self.queue) / self.capacity
    
    def get_avg_delay(self) -> float:
        """Average queuing delay"""
        if self.packets_dequeued == 0:
            return 0.0
        return self.total_queue_delay / self.packets_dequeued
    
    def is_full(self) -> bool:
        """Check if queue is full"""
        return len(self.queue) >= self.capacity
    
    def clear(self) -> None:
        """Clear all packets from queue"""
        self.queue.clear()
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "link_id": self.link_id,
            "capacity": self.capacity,
            "current_size": self.get_size(),
            "utilization": self.get_utilization(),
            "packets_enqueued": self.packets_enqueued,
            "packets_dequeued": self.packets_dequeued,
            "packets_dropped": self.packets_dropped,
            "avg_delay_ms": self.get_avg_delay(),
        }


# ============================================================================
# 2. CONGESTION CONTROLLER
# ============================================================================

class CongestionController:
    """
    Manages congestion control for network links
    Handles queue management, packet drops, and congestion window
    """
    
    def __init__(self, network_manager, animator_worker):
        """
        Initialize congestion controller
        
        Args:
            network_manager: Reference to NetworkManager
            animator_worker: Reference to AnimatorWorker
        """
        self.network_manager = network_manager
        self.animator_worker = animator_worker
        
        self.link_queues: Dict[str, LinkQueue] = {}
        self.congestion_windows: Dict[str, float] = {}  # TCP-like CWND
        self.drop_history: List[dict] = []
        self.congestion_events: List[dict] = []
        
        self.total_packets_dropped = 0
        self.enable_tcp_congestion = True  # TCP-like congestion control
    
    def create_link_queue(self, link_id: str, capacity: int,
                         drop_policy: DropPolicy = DropPolicy.TAIL_DROP) -> LinkQueue:
        """
        Create queue for a link
        
        Args:
            link_id: Link identifier
            capacity: Queue capacity (packets)
            drop_policy: Which packets to drop when full
        
        Returns:
            LinkQueue object
        """
        queue = LinkQueue(
            link_id=link_id,
            capacity=capacity,
            drop_policy=drop_policy
        )
        self.link_queues[link_id] = queue
        
        # Initialize congestion window
        self.congestion_windows[link_id] = float(capacity)
        
        return queue
    
    def process_packet_on_link(self, packet, link, current_time: float) -> bool:
        """
        Process packet on link (queueing, dropping, etc.)
        
        Args:
            packet: Packet object
            link: Link object
            current_time: Current simulation time (ms)
        
        Returns:
            True if packet accepted to queue, False if dropped
        """
        if link.id not in self.link_queues:
            # No queue configured for this link
            return True
        
        queue = self.link_queues[link.id]
        
        # Try to enqueue
        accepted = queue.enqueue(packet, current_time)
        
        if not accepted:
            # Packet dropped
            self.total_packets_dropped += 1
            self._record_drop(packet.id, link.id, current_time)
            
            # Update link color to indicate congestion
            link.update_queue_color()
            
            # TCP-like: reduce congestion window on drop
            if self.enable_tcp_congestion:
                self._handle_packet_drop(link.id)
        
        else:
            # Packet accepted
            link.current_queue = queue.get_size()
            link.update_queue_color()
            
            # TCP-like: increase congestion window on success
            if self.enable_tcp_congestion:
                self._handle_packet_success(link.id)
        
        return accepted
    
    def dequeue_packet(self, link, current_time: float) -> Optional[Tuple]:
        """
        Remove packet from link queue
        
        Args:
            link: Link object
            current_time: Current simulation time (ms)
        
        Returns:
            Tuple (packet, queuing_delay_ms) or None
        """
        if link.id not in self.link_queues:
            return None
        
        queue = self.link_queues[link.id]
        result = queue.dequeue(current_time)
        
        if result:
            link.current_queue = queue.get_size()
            link.update_queue_color()
        
        return result
    
    def _handle_packet_drop(self, link_id: str) -> None:
        """TCP-like: reduce congestion window on packet drop"""
        if link_id in self.congestion_windows:
            # TCP Reno: CWND = CWND / 2 (multiplicative decrease)
            self.congestion_windows[link_id] = max(1.0, 
                self.congestion_windows[link_id] / 2.0
            )
            self._record_congestion_event(link_id, "drop", 
                self.congestion_windows[link_id])
    
    def _handle_packet_success(self, link_id: str) -> None:
        """TCP-like: increase congestion window on packet success"""
        if link_id in self.congestion_windows:
            # TCP Reno: CWND = CWND + 1 (additive increase)
            max_cwnd = self.network_manager.links[link_id].queue_size
            self.congestion_windows[link_id] = min(float(max_cwnd),
                self.congestion_windows[link_id] + 0.1
            )
    
    def _record_drop(self, packet_id: str, link_id: str, time_ms: float) -> None:
        """Record dropped packet"""
        self.drop_history.append({
            "packet_id": packet_id,
            "link_id": link_id,
            "time_ms": time_ms
        })
    
    def _record_congestion_event(self, link_id: str, event_type: str, 
                                cwnd: float) -> None:
        """Record congestion event"""
        self.congestion_events.append({
            "link_id": link_id,
            "event_type": event_type,
            "cwnd": cwnd,
            "time_ms": self.animator_worker.sim_time
        })
    
    def get_link_queue(self, link_id: str) -> Optional[LinkQueue]:
        """Get queue for specific link"""
        return self.link_queues.get(link_id)
    
    def get_statistics(self) -> dict:
        """Get congestion statistics"""
        total_dropped = sum(q.packets_dropped for q in self.link_queues.values())
        total_enqueued = sum(q.packets_enqueued for q in self.link_queues.values())
        
        drop_rate = (total_dropped / total_enqueued * 100) if total_enqueued > 0 else 0
        
        avg_queue_depth = 0
        if self.link_queues:
            avg_queue_depth = sum(q.get_size() for q in self.link_queues.values()) / len(self.link_queues)
        
        return {
            "total_dropped": total_dropped,
            "total_enqueued": total_enqueued,
            "drop_rate": drop_rate,
            "avg_queue_depth": avg_queue_depth,
            "congestion_events": len(self.congestion_events),
        }
    
    def get_queue_history(self) -> Dict[str, List[dict]]:
        """Get queue statistics for all links"""
        return {
            link_id: queue.to_dict() 
            for link_id, queue in self.link_queues.items()
        }
    
    def clear_all(self) -> None:
        """Clear all congestion data"""
        for queue in self.link_queues.values():
            queue.clear()
        self.drop_history.clear()
        self.congestion_events.clear()
        self.total_packets_dropped = 0


# ============================================================================
# 3. ENHANCED PACKET WITH QUEUE SUPPORT
# ============================================================================

class QueueAwarePacketManager:
    """
    Extended PacketManager with queue and congestion support
    Use this instead of EnhancedPacketManager from Stage 4
    """
    
    def __init__(self, network_manager, path_manager, animator_worker,
                 latency_engine, congestion_controller: CongestionController):
        """
        Initialize queue-aware packet manager
        
        Args:
            network_manager: Reference to NetworkManager
            path_manager: Reference to PathManager
            animator_worker: Reference to AnimatorWorker
            latency_engine: Reference to LatencyThroughputEngine
            congestion_controller: Reference to CongestionController
        """
        self.network_manager = network_manager
        self.path_manager = path_manager
        self.animator_worker = animator_worker
        self.latency_engine = latency_engine
        self.congestion_controller = congestion_controller
        
        self.all_packets: List = []
        self.active_packets: Dict[str, 'Packet'] = {}
        self.queued_packets: Dict[str, List] = {}  # link_id -> packets in queue
        self.delivered_packets: List = []
        self.dropped_packets: List = []
        self.packet_counter = 0
    
    def create_packet(self, source_id: str, dest_id: str, size: int = 1024):
        """
        Create a new packet
        
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
        
        # Create metrics
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
            self.drop_packet(packet)
            return False
        
        # Get first link
        node_a_id = packet.path[0]
        node_b_id = packet.path[1]
        
        link = self.network_manager.get_link_by_nodes(node_a_id, node_b_id)
        if not link:
            self.drop_packet(packet)
            return False
        
        # ← NEW IN STAGE 5: Process through queue/congestion
        accepted = self.congestion_controller.process_packet_on_link(
            packet, link, self.animator_worker.sim_time
        )
        
        if not accepted:
            # Packet was dropped by queue
            self.drop_packet(packet)
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
                # ← NEW IN STAGE 5: Process through queue/congestion
                accepted = self.congestion_controller.process_packet_on_link(
                    packet, link, current_time
                )
                
                if not accepted:
                    # Packet dropped
                    self.drop_packet(packet)
                    return False
                
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
    
    def drop_packet(self, packet, reason: str = "congestion") -> None:
        """Mark packet as dropped"""
        from packet import PacketState
        packet.state = PacketState.DROPPED
        packet.mark_dropped()
        self.latency_engine.record_packet_drop(packet.id)
        self.dropped_packets.append(packet)
        if packet.id in self.active_packets:
            del self.active_packets[packet.id]
        self.animator_worker.remove_packet(packet.id)
    
    def get_statistics(self) -> dict:
        """Get combined statistics (latency + congestion)"""
        latency_stats = self.latency_engine.get_summary_statistics()
        congestion_stats = self.congestion_controller.get_statistics()
        
        return {
            **latency_stats,
            **congestion_stats,
        }
    
    def clear_all(self) -> None:
        """Clear all packets and metrics"""
        self.all_packets.clear()
        self.active_packets.clear()
        self.queued_packets.clear()
        self.delivered_packets.clear()
        self.dropped_packets.clear()
        self.packet_counter = 0
        self.latency_engine.clear_all()
        self.congestion_controller.clear_all()


# ============================================================================
# 4. CONGESTION METRICS DISPLAY (Enhanced for Stage 5)
# ============================================================================

class CongestionMetricsDisplay:
    """
    Display for congestion and queue metrics
    """
    
    def __init__(self, label_widget, congestion_controller: CongestionController,
                 latency_engine):
        """
        Initialize congestion metrics display
        
        Args:
            label_widget: Tkinter Label widget
            congestion_controller: Reference to CongestionController
            latency_engine: Reference to LatencyThroughputEngine
        """
        self.label = label_widget
        self.congestion_controller = congestion_controller
        self.latency_engine = latency_engine
    
    def update_display(self) -> None:
        """Update congestion metrics display"""
        stats = self.congestion_controller.get_statistics()
        latency_stats = self.latency_engine.get_summary_statistics()
        
        display_text = (
            f"═══════════════════════════════════════════════════════════\n"
            f"🔴 CONGESTION & QUEUE METRICS\n"
            f"═══════════════════════════════════════════════════════════\n"
            f"\n"
            f"📦 PACKET DROPPING\n"
            f"  Total Dropped:   {stats['total_dropped']} packets\n"
            f"  Drop Rate:       {stats['drop_rate']:.1f}%\n"
            f"  Congestion Events: {stats['congestion_events']}\n"
            f"\n"
            f"📊 QUEUE STATUS\n"
            f"  Avg Queue Depth: {stats['avg_queue_depth']:.1f} packets\n"
            f"  Total Enqueued:  {stats['total_enqueued']} packets\n"
            f"\n"
            f"⏱️  IMPACT ON LATENCY\n"
            f"  Avg Latency:     {latency_stats['avg_latency_ms']:.2f} ms\n"
            f"  Max Latency:     {latency_stats['max_latency_ms']:.2f} ms\n"
            f"  (Congestion increases latency!)\n"
            f"\n"
            f"═══════════════════════════════════════════════════════════"
        )
        
        self.label.config(text=display_text)
    
    def get_link_details(self) -> str:
        """Get detailed per-link queue stats"""
        queue_stats = self.congestion_controller.get_queue_history()
        
        if not queue_stats:
            return "No queue information available"
        
        lines = ["Per-Link Queue Statistics:"]
        for link_id, stats in queue_stats.items():
            lines.append(
                f"\n{link_id}:"
                f" {stats['current_size']}/{stats['capacity']} "
                f"({stats['utilization']*100:.0f}%) | "
                f"Dropped: {stats['packets_dropped']} | "
                f"Delay: {stats['avg_delay_ms']:.2f}ms"
            )
        
        return "\n".join(lines)

