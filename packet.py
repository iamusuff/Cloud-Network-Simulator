import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Callable
from collections import deque
import math

# ============================================================================
# 1. PACKET CLASS
# ============================================================================

class PacketState(Enum):
    """Enum for packet states"""
    QUEUED = "queued"           # Waiting at source
    IN_TRANSIT = "in_transit"   # Moving on a link
    DELIVERED = "delivered"     # Reached destination
    DROPPED = "dropped"         # Lost due to congestion


@dataclass
class Packet:
    """
    Represents a network packet traveling through the network
    """
    
    id: str                          # Unique identifier (e.g., "PKT001")
    source_node_id: str              # Starting node ID
    destination_node_id: str         # Target node ID
    creation_time: float = 0.0       # When packet was created (ms)
    sent_time: float = 0.0           # When packet started moving (ms)
    delivery_time: float = 0.0       # When packet arrived (0 if not delivered)
    size: int = 1024                 # Bytes
    state: PacketState = PacketState.QUEUED
    
    # Path information
    path: List[str] = field(default_factory=list)      # Full path of node IDs
    path_index: int = 0                                 # Current position in path
    current_node_id: str = ""                           # Current node
    current_link_index: int = 0                         # Which link traversing
    
    # Timing for animation
    link_start_time: float = 0.0    # When entered current link
    link_latency: float = 0.0       # Latency of current link
    
    def __post_init__(self):
        """Initialize packet after creation"""
        if not self.path:
            self.current_node_id = self.source_node_id
        else:
            self.current_node_id = self.path[0] if self.path else self.source_node_id
    
    def get_next_node(self) -> Optional[str]:
        """
        Look ahead to next node in path
        
        Returns:
            Next node ID, or None if at destination
        """
        if self.path_index + 1 < len(self.path):
            return self.path[self.path_index + 1]
        return None
    
    def move_to_next_link(self, current_time: float) -> bool:
        """
        Advance packet to next link in path
        
        Args:
            current_time: Current simulation time (ms)
        
        Returns:
            True if packet reached destination, False otherwise
        """
        if self.path_index + 1 >= len(self.path):
            # Already at destination
            self.state = PacketState.DELIVERED
            self.delivery_time = current_time
            return True
        
        # Move to next node
        self.path_index += 1
        self.current_node_id = self.path[self.path_index]
        self.current_link_index = self.path_index - 1
        self.link_start_time = current_time
        self.state = PacketState.IN_TRANSIT
        
        # Check if we've reached destination
        if self.path_index >= len(self.path) - 1:
            self.state = PacketState.DELIVERED
            self.delivery_time = current_time
            return True
        
        return False
    
    def get_total_latency(self) -> float:
        """
        Get total latency experienced so far
        
        Returns:
            Elapsed time from sent_time to current_time (or delivery_time if delivered)
        """
        if self.delivery_time > 0:
            return self.delivery_time - self.sent_time
        return 0.0
    
    def get_elapsed_time(self) -> float:
        """Get time since packet was sent"""
        if self.sent_time == 0:
            return 0.0
        return time.time() * 1000 - self.sent_time  # Convert to ms
    
    def mark_delivered(self, delivery_time: float) -> None:
        """Mark packet as delivered"""
        self.state = PacketState.DELIVERED
        self.delivery_time = delivery_time
    
    def mark_dropped(self) -> None:
        """Mark packet as dropped"""
        self.state = PacketState.DROPPED
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "destination_node_id": self.destination_node_id,
            "state": self.state.value,
            "path": self.path,
            "path_index": self.path_index,
            "creation_time": self.creation_time,
            "sent_time": self.sent_time,
            "delivery_time": self.delivery_time,
            "total_latency": self.get_total_latency(),
            "size": self.size,
        }


# ============================================================================
# 2. PACKET ANIMATOR
# ============================================================================

@dataclass
class PacketAnimator:
    """
    Manages animation of a single packet on a link
    """
    
    packet: Packet
    node_a_pos: Tuple[float, float]  # Start position
    node_b_pos: Tuple[float, float]  # End position
    link_latency: float              # Latency in ms
    start_time: float                # When animation started (ms)
    speed_multiplier: float = 1.0    # Animation speed (1.0 = real-time)
    
    def update(self, current_time: float) -> bool:
        """
        Update packet position
        
        Args:
            current_time: Current simulation time (ms)
        
        Returns:
            True if packet finished link, False otherwise
        """
        elapsed = (current_time - self.start_time) / self.speed_multiplier
        duration = self.link_latency
        
        if elapsed >= duration:
            return True  # Link traversal complete
        
        return False
    
    def get_current_position(self, current_time: float) -> Tuple[float, float]:
        """
        Get interpolated position of packet
        
        Args:
            current_time: Current simulation time (ms)
        
        Returns:
            (x, y) position
        """
        progress = self.get_progress(current_time)
        progress = min(1.0, max(0.0, progress))  # Clamp 0-1
        
        x1, y1 = self.node_a_pos
        x2, y2 = self.node_b_pos
        
        # Linear interpolation
        x = x1 + (x2 - x1) * progress
        y = y1 + (y2 - y1) * progress
        
        return (x, y)
    
    def get_progress(self, current_time: float) -> float:
        """
        Get progress along link (0.0 to 1.0)
        
        Args:
            current_time: Current simulation time (ms)
        
        Returns:
            Progress from 0.0 (start) to 1.0 (end)
        """
        elapsed = (current_time - self.start_time) / self.speed_multiplier
        duration = self.link_latency
        
        if duration == 0:
            return 1.0
        
        return elapsed / duration


# ============================================================================
# 3. ANIMATION WORKER (Threading)
# ============================================================================

class AnimatorWorker(threading.Thread):
    """
    Background thread for smooth packet animation
    Prevents UI freezing during animation
    """
    
    def __init__(self, update_callback: Callable, frame_rate: int = 30):
        """
        Initialize animator worker thread
        
        Args:
            update_callback: Function called each frame with (packets, animators)
            frame_rate: Target FPS (default 30)
        """
        super().__init__(daemon=True)
        self.active_packets: Dict[str, Packet] = {}
        self.animators: Dict[str, PacketAnimator] = {}
        self.simulation_running = False
        self.paused = False
        self.update_callback = update_callback
        self.frame_rate = frame_rate
        self.frame_time = 1000.0 / frame_rate  # ms per frame
        self._lock = threading.Lock()
        self.speed_multiplier = 1.0
        self.start_time = None
        self.sim_time = 0.0  # Simulation time (ms)
    
    def run(self) -> None:
        """Main thread loop"""
        self.simulation_running = True
        self.start_time = time.time() * 1000  # ms
        
        while self.simulation_running:
            if not self.paused:
                # Calculate current simulation time
                self.sim_time = (time.time() * 1000 - self.start_time) * self.speed_multiplier
                
                # Update all active animations
                self._update_all_packets()
                
                # Trigger UI update
                if self.update_callback:
                    with self._lock:
                        self.update_callback(
                            dict(self.active_packets),
                            dict(self.animators),
                            self.sim_time
                        )
            
            # Control frame rate
            time.sleep(self.frame_time / 1000.0)
    
    def _update_all_packets(self) -> None:
        """Update all active packet animations"""
        with self._lock:
            finished_packets = []
            
            for pkt_id, animator in list(self.animators.items()):
                # Check if link traversal complete
                if animator.update(self.sim_time):
                    finished_packets.append(pkt_id)
            
            # Remove finished animators
            for pkt_id in finished_packets:
                del self.animators[pkt_id]
    
    def add_packet(self, packet: Packet, node_a_pos: Tuple[float, float],
                  node_b_pos: Tuple[float, float], link_latency: float) -> None:
        """
        Add packet to animation queue
        
        Args:
            packet: Packet object
            node_a_pos: Starting node position
            node_b_pos: Ending node position
            link_latency: Link latency in ms
        """
        with self._lock:
            self.active_packets[packet.id] = packet
            animator = PacketAnimator(
                packet=packet,
                node_a_pos=node_a_pos,
                node_b_pos=node_b_pos,
                link_latency=link_latency,
                start_time=self.sim_time,
                speed_multiplier=self.speed_multiplier
            )
            self.animators[packet.id] = animator
    
    def remove_packet(self, packet_id: str) -> None:
        """Remove packet from animation"""
        with self._lock:
            if packet_id in self.active_packets:
                del self.active_packets[packet_id]
            if packet_id in self.animators:
                del self.animators[packet_id]
    
    def pause(self) -> None:
        """Pause animation"""
        self.paused = True
    
    def resume(self) -> None:
        """Resume animation"""
        self.paused = False
    
    def stop(self) -> None:
        """Stop animation thread"""
        self.simulation_running = False
        self.join(timeout=1.0)
    
    def get_packet_position(self, packet_id: str) -> Optional[Tuple[float, float]]:
        """Get current position of packet"""
        with self._lock:
            if packet_id in self.animators:
                animator = self.animators[packet_id]
                return animator.get_current_position(self.sim_time)
        return None
    
    def set_speed(self, multiplier: float) -> None:
        """Set animation speed multiplier (1.0 = real-time)"""
        self.speed_multiplier = max(0.1, multiplier)


# ============================================================================
# 4. PACKET MANAGER
# ============================================================================

class PacketManager:
    """
    Manages packet creation, routing, and lifecycle
    """
    
    def __init__(self, network_manager, path_manager, animator_worker: AnimatorWorker):
        """
        Initialize packet manager
        
        Args:
            network_manager: Reference to NetworkManager
            path_manager: Reference to PathManager
            animator_worker: Reference to AnimatorWorker thread
        """
        self.network_manager = network_manager
        self.path_manager = path_manager
        self.animator_worker = animator_worker
        self.all_packets: List[Packet] = []
        self.active_packets: Dict[str, Packet] = {}  # Currently moving
        self.delivered_packets: List[Packet] = []
        self.dropped_packets: List[Packet] = []
        self.packet_counter = 0
    
    def create_packet(self, source_id: str, dest_id: str, size: int = 1024) -> Optional[Packet]:
        """
        Create a new packet
        
        Args:
            source_id: Source node ID
            dest_id: Destination node ID
            size: Packet size in bytes
        
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
        
        # Get path using path manager
        if not self.path_manager.set_path(source_id, dest_id):
            return None
        
        path_nodes = self.path_manager.get_current_path_nodes()
        
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
        
        return packet
    
    def start_packet_animation(self, packet: Packet) -> bool:
        """
        Start animating a packet on first link
        
        Args:
            packet: Packet to animate
        
        Returns:
            True if animation started, False otherwise
        """
        if len(packet.path) < 2:
            packet.mark_dropped()
            return False
        
        # Get first link
        node_a_id = packet.path[0]
        node_b_id = packet.path[1]
        
        link = self.network_manager.get_link_by_nodes(node_a_id, node_b_id)
        if not link:
            packet.mark_dropped()
            return False
        
        node_a = self.network_manager.nodes[node_a_id]
        node_b = self.network_manager.nodes[node_b_id]
        
        packet.state = PacketState.IN_TRANSIT
        packet.current_link_index = 0
        packet.link_latency = link.latency
        
        # Add to animator
        self.animator_worker.add_packet(
            packet,
            (node_a.x, node_a.y),
            (node_b.x, node_b.y),
            link.latency
        )
        
        return True
    
    def advance_packet(self, packet: Packet) -> bool:
        """
        Move packet to next link in path
        
        Args:
            packet: Packet to advance
        
        Returns:
            True if packet reached destination, False otherwise
        """
        current_time = self.animator_worker.sim_time
        
        if packet.move_to_next_link(current_time):
            # Reached destination
            packet.mark_delivered(current_time)
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
    
    def drop_packet(self, packet: Packet) -> None:
        """Mark packet as dropped"""
        packet.mark_dropped()
        self.dropped_packets.append(packet)
        if packet.id in self.active_packets:
            del self.active_packets[packet.id]
        self.animator_worker.remove_packet(packet.id)
    
    def get_statistics(self) -> dict:
        """Get packet statistics"""
        total = len(self.all_packets)
        delivered = len(self.delivered_packets)
        dropped = len(self.dropped_packets)
        active = len(self.active_packets)
        
        return {
            "total_packets": total,
            "delivered": delivered,
            "dropped": dropped,
            "active": active,
            "delivery_rate": (delivered / total * 100) if total > 0 else 0,
            "drop_rate": (dropped / total * 100) if total > 0 else 0,
        }
    
    def clear_all(self) -> None:
        """Clear all packets"""
        self.all_packets.clear()
        self.active_packets.clear()
        self.delivered_packets.clear()
        self.dropped_packets.clear()
        self.packet_counter = 0

