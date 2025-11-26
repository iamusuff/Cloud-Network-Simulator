# ============================================================================
# Cloud Network Simulator - Stage 1: GUI + Topology Editor
# ============================================================================
# Main project structure with Node, Link, NetworkManager, and basic GUI
# ============================================================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import networkx as nx
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math
import json
from datetime import datetime
from routing.router import DijkstraRouter, PathManager, PathInfo, MetricsDisplay
from packet import (
        Packet, PacketState, PacketAnimator, 
        AnimatorWorker, PacketManager
    )
from latency import (
    LatencyThroughputEngine, EnhancedPacketManager, 
    EnhancedMetricsDisplay, PacketMetrics
)
from congestion import (
    CongestionController, LinkQueue, DropPolicy,
    QueueAwarePacketManager, CongestionMetricsDisplay
)
from export import DataExportEngine, SimulationReportGenerator

# ============================================================================
# 1. CONFIGURATION
# ============================================================================

class Config:
    """Global configuration constants"""
    
    # Canvas settings
    CANVAS_WIDTH = 1000
    CANVAS_HEIGHT = 600
    CANVAS_BG_COLOR = "white"
    
    # Node settings
    NODE_RADIUS = 20
    NODE_COLOR_DEFAULT = "lightblue"
    NODE_COLOR_SOURCE = "lightgreen"
    NODE_COLOR_DEST = "lightyellow"
    NODE_COLOR_SELECTED = "cyan"
    NODE_TEXT_COLOR = "black"
    
    # Link settings
    LINK_COLOR_DEFAULT = "black"
    LINK_COLOR_NORMAL = "green"
    LINK_COLOR_CONGESTED = "yellow"
    LINK_COLOR_CRITICAL = "red"
    LINK_WIDTH_DEFAULT = 2
    LINK_WIDTH_HIGHLIGHTED = 4
    
    # Validation
    MIN_LATENCY = 0.1
    MAX_LATENCY = 100.0
    MIN_BANDWIDTH = 1.0
    MAX_BANDWIDTH = 10000.0
    MIN_QUEUE_SIZE = 1
    MAX_QUEUE_SIZE = 1000
    
    # UI Layout
    CONTROL_PANEL_WIDTH = 280
    METRICS_PANEL_HEIGHT = 150
    WINDOW_WIDTH = 1400
    WINDOW_HEIGHT = 900
    WINDOW_TITLE = "Cloud Network Simulator"


# ============================================================================
# 2. DATA MODELS
# ============================================================================

@dataclass
class Node:
    """Represents a network node (router, host, etc.)"""
    
    id: str
    label: str
    x: float
    y: float
    radius: int = Config.NODE_RADIUS
    color: str = Config.NODE_COLOR_DEFAULT
    is_source: bool = False
    is_destination: bool = False
    connected_links: List['Link'] = field(default_factory=list)
    
    def get_position(self) -> Tuple[float, float]:
        """Return node position"""
        return (self.x, self.y)
    
    def set_position(self, x: float, y: float) -> None:
        """Update node position"""
        self.x = x
        self.y = y
    
    def add_link(self, link: 'Link') -> None:
        """Add a connected link"""
        if link not in self.connected_links:
            self.connected_links.append(link)
    
    def remove_link(self, link: 'Link') -> None:
        """Remove a connected link"""
        if link in self.connected_links:
            self.connected_links.remove(link)
    
    def get_connected_nodes(self) -> List['Node']:
        """Get all directly connected nodes"""
        connected = []
        for link in self.connected_links:
            if link.node_a == self:
                connected.append(link.node_b)
            else:
                connected.append(link.node_a)
        return connected
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "is_source": self.is_source,
            "is_destination": self.is_destination,
        }


@dataclass
class Link:
    """Represents a network link (connection between nodes)"""
    
    id: str
    node_a: Node
    node_b: Node
    latency: float  # milliseconds
    bandwidth: float  # Mbps
    queue_size: int  # packets
    current_queue: int = 0
    packets_dropped: int = 0
    is_bidirectional: bool = True
    color: str = Config.LINK_COLOR_DEFAULT
    
    def __post_init__(self):
        """Register link with nodes"""
        self.node_a.add_link(self)
        self.node_b.add_link(self)
    
    def get_length(self) -> float:
        """Calculate Euclidean distance between nodes"""
        dx = self.node_b.x - self.node_a.x
        dy = self.node_b.y - self.node_a.y
        return math.sqrt(dx**2 + dy**2)
    
    def get_midpoint(self) -> Tuple[float, float]:
        """Get midpoint of link for label placement"""
        return (
            (self.node_a.x + self.node_b.x) / 2,
            (self.node_a.y + self.node_b.y) / 2
        )
    
    def update_queue_color(self) -> None:
        """Update link color based on queue utilization"""
        if self.queue_size == 0:
            self.color = Config.LINK_COLOR_DEFAULT
            return
        
        utilization = self.current_queue / self.queue_size
        if utilization >= 0.9:
            self.color = Config.LINK_COLOR_CRITICAL
        elif utilization >= 0.5:
            self.color = Config.LINK_COLOR_CONGESTED
        else:
            self.color = Config.LINK_COLOR_NORMAL
    
    def get_queue_utilization(self) -> float:
        """Return queue utilization (0.0 to 1.0)"""
        if self.queue_size == 0:
            return 0.0
        return min(1.0, self.current_queue / self.queue_size)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "node_a_id": self.node_a.id,
            "node_b_id": self.node_b.id,
            "latency": self.latency,
            "bandwidth": self.bandwidth,
            "queue_size": self.queue_size,
            "is_bidirectional": self.is_bidirectional,
        }


# ============================================================================
# 3. NETWORK MANAGER
# ============================================================================

class NetworkManager:
    """Manages network topology (nodes and links)"""
    
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.links: Dict[str, Link] = {}
        self.graph = nx.Graph()
        self.node_counter = 0
        self.link_counter = 0
        self.selected_source: Optional[Node] = None
        self.selected_destination: Optional[Node] = None
    
    def add_node(self, x: float, y: float, label: str = None) -> Node:
        """Add a new node to the network"""
        # Validate position
        if not (0 <= x <= Config.CANVAS_WIDTH and 0 <= y <= Config.CANVAS_HEIGHT):
            raise ValueError("Node position out of canvas bounds")
        
        # Check for duplicate position
        for node in self.nodes.values():
            dist = math.sqrt((node.x - x)**2 + (node.y - y)**2)
            if dist < Config.NODE_RADIUS * 2:
                raise ValueError("Node too close to existing node")
        
        self.node_counter += 1
        node_id = f"N{self.node_counter}"
        node_label = label or f"Node{self.node_counter}"
        
        node = Node(
            id=node_id,
            label=node_label,
            x=x,
            y=y
        )
        
        self.nodes[node_id] = node
        self.graph.add_node(node_id, label=node_label)
        
        return node
    
    def remove_node(self, node_id: str) -> bool:
        """Remove a node and all connected links"""
        if node_id not in self.nodes:
            return False
        
        node = self.nodes[node_id]
        
        # Remove all connected links
        links_to_remove = list(node.connected_links)
        for link in links_to_remove:
            self.remove_link(link.id)
        
        # Remove from graph and storage
        self.graph.remove_node(node_id)
        del self.nodes[node_id]
        
        return True
    
    def add_link(self, node_a_id: str, node_b_id: str, 
                 latency: float, bandwidth: float, queue_size: int) -> Optional[Link]:
        """Add a new link between two nodes"""
        
        # Validate nodes exist
        if node_a_id not in self.nodes or node_b_id not in self.nodes:
            raise ValueError("One or both nodes do not exist")
        
        # Prevent self-loops
        if node_a_id == node_b_id:
            raise ValueError("Cannot create self-loop")
        
        # Check for duplicate link
        for link in self.links.values():
            if (link.node_a.id == node_a_id and link.node_b.id == node_b_id) or \
               (link.node_a.id == node_b_id and link.node_b.id == node_a_id):
                raise ValueError("Link already exists between these nodes")
        
        # Validate parameters
        if not (Config.MIN_LATENCY <= latency <= Config.MAX_LATENCY):
            raise ValueError(f"Latency must be {Config.MIN_LATENCY}-{Config.MAX_LATENCY} ms")
        if not (Config.MIN_BANDWIDTH <= bandwidth <= Config.MAX_BANDWIDTH):
            raise ValueError(f"Bandwidth must be {Config.MIN_BANDWIDTH}-{Config.MAX_BANDWIDTH} Mbps")
        if not (Config.MIN_QUEUE_SIZE <= queue_size <= Config.MAX_QUEUE_SIZE):
            raise ValueError(f"Queue size must be {Config.MIN_QUEUE_SIZE}-{Config.MAX_QUEUE_SIZE}")
        
        self.link_counter += 1
        link_id = f"L{self.link_counter}"
        
        node_a = self.nodes[node_a_id]
        node_b = self.nodes[node_b_id]
        
        link = Link(
            id=link_id,
            node_a=node_a,
            node_b=node_b,
            latency=latency,
            bandwidth=bandwidth,
            queue_size=queue_size
        )
        
        self.links[link_id] = link
        self.graph.add_edge(node_a_id, node_b_id, 
                           weight=latency, 
                           bandwidth=bandwidth,
                           link_id=link_id)
        
        return link
    
    def remove_link(self, link_id: str) -> bool:
        """Remove a link"""
        if link_id not in self.links:
            return False
        
        link = self.links[link_id]
        
        # Unregister from nodes
        link.node_a.remove_link(link)
        link.node_b.remove_link(link)
        
        # Remove from graph
        self.graph.remove_edge(link.node_a.id, link.node_b.id)
        
        del self.links[link_id]
        return True
    
    def get_node_by_pos(self, x: float, y: float, tolerance: int = 25) -> Optional[Node]:
        """Get node at canvas position (within tolerance radius)"""
        for node in self.nodes.values():
            dist = math.sqrt((node.x - x)**2 + (node.y - y)**2)
            if dist <= tolerance:
                return node
        return None
    
    def get_link_by_nodes(self, node_a_id: str, node_b_id: str) -> Optional[Link]:
        """Get link between two nodes"""
        for link in self.links.values():
            if (link.node_a.id == node_a_id and link.node_b.id == node_b_id) or \
               (link.node_a.id == node_b_id and link.node_b.id == node_a_id):
                return link
        return None
    
    def update_networkx_graph(self) -> None:
        """Rebuild NetworkX graph from current topology"""
        self.graph = nx.Graph()
        
        for node_id, node in self.nodes.items():
            self.graph.add_node(node_id, label=node.label)
        
        for link in self.links.values():
            self.graph.add_edge(link.node_a.id, link.node_b.id,
                               weight=link.latency,
                               bandwidth=link.bandwidth,
                               link_id=link.id)
    
    def clear_all(self) -> None:
        """Clear entire network"""
        self.nodes.clear()
        self.links.clear()
        self.graph.clear()
        self.node_counter = 0
        self.link_counter = 0
        self.selected_source = None
        self.selected_destination = None
    
    def to_dict(self) -> dict:
        """Serialize network to dictionary"""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "links": [link.to_dict() for link in self.links.values()],
            "timestamp": datetime.now().isoformat()
        }


# ============================================================================
# 4. CANVAS RENDERER
# ============================================================================

class CanvasRenderer:
    """Handles all Tkinter canvas drawing operations"""
    
    def __init__(self, canvas: tk.Canvas, network_manager: NetworkManager):
        self.canvas = canvas
        self.network_manager = network_manager
        self.node_graphics: Dict[str, int] = {}  # node_id -> canvas oval id
        self.link_graphics: Dict[str, int] = {}  # link_id -> canvas line id
        self.link_labels: Dict[str, int] = {}    # link_id -> canvas text id
        self.highlighted_links: List[int] = []
        self.dragged_node: Optional[Node] = None
    
    def draw_node(self, node: Node) -> int:
        """Draw a node on canvas"""
        x, y = node.x, node.y
        r = node.radius
        
        # Draw circle
        oval_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=node.color,
            outline="black",
            width=2,
            tags=f"node_{node.id}"
        )
        
        # Draw label
        self.canvas.create_text(
            x, y,
            text=node.label,
            font=("Arial", 9, "bold"),
            fill=Config.NODE_TEXT_COLOR,
            tags=f"node_label_{node.id}"
        )
        
        self.node_graphics[node.id] = oval_id
        return oval_id
    
    def draw_link(self, link: Link) -> int:
        """Draw a link on canvas"""
        x1, y1 = link.node_a.x, link.node_a.y
        x2, y2 = link.node_b.x, link.node_b.y
        
        # Draw line
        line_id = self.canvas.create_line(
            x1, y1, x2, y2,
            fill=link.color,
            width=Config.LINK_WIDTH_DEFAULT,
            tags=f"link_{link.id}"
        )
        
        # Draw label at midpoint
        mx, my = link.get_midpoint()
        label_text = f"{link.latency}ms\n{link.bandwidth}Mbps"
        text_id = self.canvas.create_text(
            mx, my,
            text=label_text,
            font=("Arial", 8),
            fill="darkblue",
            background="lightyellow",
            tags=f"link_label_{link.id}"
        )
        
        self.link_graphics[link.id] = line_id
        self.link_labels[link.id] = text_id
        return line_id
    
    def update_node_position(self, node_id: str, x: float, y: float) -> None:
        """Update node position and redraw connected links"""
        if node_id not in self.node_graphics:
            return
        
        node = self.network_manager.nodes[node_id]
        r = node.radius
        
        # Update node position
        oval_id = self.node_graphics[node_id]
        self.canvas.coords(oval_id, x - r, y - r, x + r, y + r)
        
        # Update label position
        self.canvas.coords(f"node_label_{node_id}", x, y)
        
        # Update node object
        node.set_position(x, y)
        
        # Redraw connected links
        for link in node.connected_links:
            self._redraw_link(link)
    
    def _redraw_link(self, link: Link) -> None:
        """Redraw a link (used when nodes move)"""
        if link.id not in self.link_graphics:
            return
        
        x1, y1 = link.node_a.x, link.node_a.y
        x2, y2 = link.node_b.x, link.node_b.y
        
        # Update line
        line_id = self.link_graphics[link.id]
        self.canvas.coords(line_id, x1, y1, x2, y2)
        
        # Update label
        mx, my = link.get_midpoint()
        text_id = self.link_labels[link.id]
        self.canvas.coords(text_id, mx, my)
    
    def highlight_link(self, link: Link) -> int:
        """Highlight a link with thicker yellow line"""
        x1, y1 = link.node_a.x, link.node_a.y
        x2, y2 = link.node_b.x, link.node_b.y
        
        line_id = self.canvas.create_line(
            x1, y1, x2, y2,
            fill="yellow",
            width=Config.LINK_WIDTH_HIGHLIGHTED,
            tags="highlighted_link"
        )
        
        self.highlighted_links.append(line_id)
        # Move to back so regular links appear on top
        self.canvas.tag_lower(line_id)
        return line_id
    
    def clear_highlights(self) -> None:
        """Clear all highlighted links"""
        for line_id in self.highlighted_links:
            self.canvas.delete(line_id)
        self.highlighted_links.clear()
    
    def redraw_all(self) -> None:
        """Redraw entire canvas"""
        self.canvas.delete("all")
        self.node_graphics.clear()
        self.link_graphics.clear()
        self.link_labels.clear()
        
        # Draw all links first (so they appear behind nodes)
        for link in self.network_manager.links.values():
            self.draw_link(link)
        
        # Draw all nodes on top
        for node in self.network_manager.nodes.values():
            self.draw_node(node)


# ============================================================================
# 5. CONTROL PANEL
# ============================================================================

class ControlPanel:
    """UI control panel for network operations"""
    
    def __init__(self, parent: tk.Frame, network_manager: NetworkManager, 
                 canvas_renderer: CanvasRenderer, update_callback):
        self.frame = parent
        self.network_manager = network_manager
        self.canvas_renderer = canvas_renderer
        self.update_callback = update_callback
        
        self._create_widgets()
    
    def _create_widgets(self) -> None:
        """Create all control panel widgets"""
        
        # Title
        title = tk.Label(self.frame, text="🔧 Topology Editor", 
                        font=("Arial", 12, "bold"))
        title.pack(pady=10)
        
        # Separator
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)
        
        # ========== NODE OPERATIONS ==========
        tk.Label(self.frame, text="Node Operations", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        btn_add_node = tk.Button(self.frame, text="➕ Add Node (Click Canvas)",
                                command=self._on_add_node, 
                                bg="#90EE90", width=25)
        btn_add_node.pack(pady=5, padx=10)
        
        # Node label input
        tk.Label(self.frame, text="Node Label:", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.node_label_var = tk.StringVar(value="")
        entry = tk.Entry(self.frame, textvariable=self.node_label_var, width=27)
        entry.pack(padx=10, pady=(0, 5))
        
        btn_del_node = tk.Button(self.frame, text="🗑️ Delete Node",
                                command=self._on_delete_node,
                                bg="#FFB6C6", width=25)
        btn_del_node.pack(pady=5, padx=10)
        
        # Separator
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)
        
        # ========== LINK OPERATIONS ==========
        tk.Label(self.frame, text="Link Operations", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        # Source node
        tk.Label(self.frame, text="Source Node:", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.source_var = tk.StringVar()
        self.source_combo = ttk.Combobox(self.frame, textvariable=self.source_var,
                                         state="readonly", width=24)
        self.source_combo.pack(padx=10, pady=(0, 5))
        
        # Destination node
        tk.Label(self.frame, text="Dest Node:", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.dest_var = tk.StringVar()
        self.dest_combo = ttk.Combobox(self.frame, textvariable=self.dest_var,
                                       state="readonly", width=24)
        self.dest_combo.pack(padx=10, pady=(0, 5))
        
        # Latency
        tk.Label(self.frame, text="Latency (ms):", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.latency_var = tk.DoubleVar(value=5.0)
        tk.Spinbox(self.frame, from_=Config.MIN_LATENCY, to=Config.MAX_LATENCY,
                  textvariable=self.latency_var, width=25).pack(padx=10, pady=(0, 5))
        
        # Bandwidth
        tk.Label(self.frame, text="Bandwidth (Mbps):", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.bandwidth_var = tk.DoubleVar(value=100.0)
        tk.Spinbox(self.frame, from_=Config.MIN_BANDWIDTH, to=Config.MAX_BANDWIDTH,
                  textvariable=self.bandwidth_var, width=25).pack(padx=10, pady=(0, 5))
        
        # Queue size
        tk.Label(self.frame, text="Queue Size (packets):", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.queue_var = tk.IntVar(value=50)
        tk.Spinbox(self.frame, from_=Config.MIN_QUEUE_SIZE, to=Config.MAX_QUEUE_SIZE,
                  textvariable=self.queue_var, width=25).pack(padx=10, pady=(0, 5))
        
        btn_add_link = tk.Button(self.frame, text="➕ Add Link",
                                command=self._on_add_link,
                                bg="#87CEEB", width=25)
        btn_add_link.pack(pady=5, padx=10)
        
        btn_del_link = tk.Button(self.frame, text="🗑️ Delete Link",
                                command=self._on_delete_link,
                                bg="#FFB6C6", width=25)
        btn_del_link.pack(pady=5, padx=10)
        
        # Separator
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)
        
        # ========== ROUTING OPERATIONS (NEW IN STAGE 2) ==========
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)

        tk.Label(self.frame, text="Routing", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        btn_compute = tk.Button(self.frame, text="🗺️ Compute Path (Dijkstra)",
                                command=self._on_compute_path,
                                bg="#FFD700", width=25, font=("Arial", 9, "bold"))
        btn_compute.pack(pady=5, padx=10)

        btn_clear_path = tk.Button(self.frame, text="❌ Clear Path",
                                command=self._on_clear_path,
                                bg="#FFB6C6", width=25)
        btn_clear_path.pack(pady=5, padx=10)

        # ========== PACKET OPERATIONS (NEW IN STAGE 3) ==========
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)

        tk.Label(self.frame, text="Packet Sending", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        tk.Label(self.frame, text="Packet Size (bytes):", font=("Arial", 9)).pack(anchor="w", padx=10)
        self.packet_size_var = tk.IntVar(value=1024)
        tk.Spinbox(self.frame, from_=64, to=65535,
                textvariable=self.packet_size_var, width=25).pack(padx=10, pady=(0, 5))

        btn_send_one = tk.Button(self.frame, text="📤 Send 1 Packet",
                                command=self._on_send_packet,
                                bg="#90EE90", width=25)
        btn_send_one.pack(pady=5, padx=10)

        btn_send_burst = tk.Button(self.frame, text="📤 Send 10 Packets",
                                command=self._on_send_burst,
                                bg="#90EE90", width=25)
        btn_send_burst.pack(pady=5, padx=10)

        btn_start_sim = tk.Button(self.frame, text="▶️ Start Simulation",
                                command=self._on_start_simulation,
                                bg="#87CEEB", width=25, font=("Arial", 9, "bold"))
        btn_start_sim.pack(pady=5, padx=10)

        btn_pause_sim = tk.Button(self.frame, text="⏸️ Pause Simulation",
                                command=self._on_pause_simulation,
                                bg="#FFD700", width=25)
        btn_pause_sim.pack(pady=5, padx=10)

        # ========== UTILITIES ==========
        tk.Label(self.frame, text="Utilities", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        btn_view_metrics = tk.Button(self.frame, text="📊 View Packet Metrics",
                                    command=self._on_view_packet_metrics,
                                    bg="#E6E6FA", width=25)
        btn_view_metrics.pack(pady=5, padx=10)

        # ========== DATA EXPORT (NEW IN STAGE 6) ==========
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)

        tk.Label(self.frame, text="Data Export", 
                font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 5))

        btn_export_all = tk.Button(self.frame, text="💾 Export All Data",
                                command=self._on_export_all,
                                bg="#DDA0DD", width=25, font=("Arial", 9, "bold"))
        btn_export_all.pack(pady=5, padx=10)

        btn_export_metrics = tk.Button(self.frame, text="📊 Export Metrics (CSV)",
                                    command=self._on_export_metrics,
                                    bg="#98FB98", width=25)
        btn_export_metrics.pack(pady=5, padx=10)

        btn_export_congestion = tk.Button(self.frame, text="🔴 Export Congestion (CSV)",
                                        command=self._on_export_congestion,
                                        bg="#FFB6C1", width=25)
        btn_export_congestion.pack(pady=5, padx=10)

        btn_export_report = tk.Button(self.frame, text="📄 Export Report (TXT)",
                                    command=self._on_export_report,
                                    bg="#F0E68C", width=25)
        btn_export_report.pack(pady=5, padx=10)

        # ========== UTILITIES ==========
        ttk.Separator(self.frame, orient="horizontal").pack(fill="x", pady=5)

        btn_clear = tk.Button(self.frame, text="🔄 Clear All",
                             command=self._on_clear_all,
                             bg="#FFD700", width=25)
        btn_clear.pack(pady=5, padx=10)
        
        btn_save = tk.Button(self.frame, text="💾 Save Topology",
                            command=self._on_save, width=25)
        btn_save.pack(pady=5, padx=10)
        
        btn_load = tk.Button(self.frame, text="📂 Load Topology",
                            command=self._on_load, width=25)
        btn_load.pack(pady=5, padx=10)
    
    def update_node_list(self) -> None:
        """Update node dropdown lists"""
        node_list = [f"{nid}: {self.network_manager.nodes[nid].label}" 
                     for nid in sorted(self.network_manager.nodes.keys())]
        self.source_combo["values"] = node_list
        self.dest_combo["values"] = node_list
    
    def _on_add_node(self) -> None:
        """Trigger add node mode"""
        messagebox.showinfo("Add Node", "Click on the canvas to place a node")
        self.canvas_renderer.canvas.config(cursor="crosshair")
    
    def _on_delete_node(self) -> None:
        """Delete selected node"""
        if not self.source_var.get():
            messagebox.showwarning("Warning", "Please select a node to delete")
            return
        
        node_id = self.source_var.get().split(":")[0]
        if self.network_manager.remove_node(node_id):
            self.update_node_list()
            self.canvas_renderer.redraw_all()
            self.update_callback()
            messagebox.showinfo("Success", f"Node {node_id} deleted")
    
    def _on_add_link(self) -> None:
        """Add link between selected nodes"""
        src = self.source_var.get()
        dst = self.dest_var.get()
        
        if not src or not dst:
            messagebox.showwarning("Warning", "Please select both source and destination")
            return
        
        src_id = src.split(":")[0]
        dst_id = dst.split(":")[0]
        
        try:
            self.network_manager.add_link(
                src_id, dst_id,
                self.latency_var.get(),
                self.bandwidth_var.get(),
                self.queue_var.get()
            )
            self.canvas_renderer.redraw_all()
            self.update_callback()
            messagebox.showinfo("Success", f"Link created: {src_id} ↔ {dst_id}")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
    
    def _on_delete_link(self) -> None:
        """Delete selected link"""
        src = self.source_var.get()
        dst = self.dest_var.get()
        
        if not src or not dst:
            messagebox.showwarning("Warning", "Please select both endpoints")
            return
        
        src_id = src.split(":")[0]
        dst_id = dst.split(":")[0]
        
        link = self.network_manager.get_link_by_nodes(src_id, dst_id)
        if link:
            self.network_manager.remove_link(link.id)
            self.canvas_renderer.redraw_all()
            self.update_callback()
            messagebox.showinfo("Success", f"Link deleted")
        else:
            messagebox.showwarning("Warning", "Link not found")
    
    def _on_clear_all(self) -> None:
        """Clear entire network"""
        # ← UPDATE THIS (add confirmation about exporting)
        if messagebox.askyesno("Confirm Clear", 
            "Clear entire network? (You can export data first)"):
            self.network_manager.clear_all()
            self.canvas_renderer.redraw_all()
            self.update_node_list()
            self.update_callback()
            messagebox.showinfo("Success", "Network cleared")
    
    def _on_save(self) -> None:
        """Save topology to JSON"""
        if not self.network_manager.nodes:
            messagebox.showwarning("Warning", "Network is empty")
            return
        
        filename = f"topology_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(self.network_manager.to_dict(), f, indent=2)
            messagebox.showinfo("Success", f"Topology saved to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def _on_load(self) -> None:
        """Load topology from JSON (simplified)"""
        messagebox.showinfo("Info", "Load feature coming in next stage")

    def _on_compute_path(self) -> None:
        """Compute shortest path using Dijkstra"""
        src = self.source_var.get()
        dst = self.dest_var.get()
        
        if not src or not dst:
            messagebox.showwarning("Warning", 
                "Please select both source and destination nodes")
            return
        
        src_id = src.split(":")[0]
        dst_id = dst.split(":")[0]
        
        if src_id == dst_id:
            messagebox.showwarning("Warning", "Source and destination must differ")
            return
        
        # Compute path
        success = self.network_manager.path_manager.set_path(src_id, dst_id)
        
        if not success:
            messagebox.showwarning("No Path", 
                f"No path exists between {src_id} and {dst_id}")
            self.canvas_renderer.clear_highlights()
            return
        
        # Get path info
        path_info = self.network_manager.path_manager.get_current_path()
        path_nodes = self.network_manager.path_manager.get_current_path_nodes()
        
        # Highlight path on canvas
        self.canvas_renderer.clear_highlights()
        for i in range(len(path_nodes) - 1):
            link = self.network_manager.get_link_by_nodes(
                path_nodes[i], path_nodes[i + 1]
            )
            if link:
                self.canvas_renderer.highlight_link(link)
        
        # Update metrics display
        if hasattr(self.network_manager, 'main_window'):
            self.network_manager.main_window.update_metrics_display(path_info)
        
        # Show success message
        messagebox.showinfo("Path Found", 
            f"Path: {' → '.join(path_nodes)}\n"
            f"Hops: {path_info.hop_count}\n"
            f"Total Latency: {path_info.total_latency:.2f} ms\n"
            f"Throughput: {path_info.throughput:.1f} Mbps")

    def _on_clear_path(self) -> None:
        """Clear current path"""
        self.network_manager.path_manager.clear_path()
        self.canvas_renderer.clear_highlights()
        self.update_callback()

    def _on_send_packet(self) -> None:
        """Send a single packet"""
        src = self.source_var.get()
        dst = self.dest_var.get()
        
        if not src or not dst:
            messagebox.showwarning("Warning", "Select source and destination")
            return
        
        src_id = src.split(":")[0]
        dst_id = dst.split(":")[0]
        
        packet = self.network_manager.packet_manager.create_packet(
            src_id, dst_id, 
            self.packet_size_var.get()
        )
        
        if packet:
            self.network_manager.packet_manager.start_packet_animation(packet)
            messagebox.showinfo("Success", f"Packet {packet.id} sent!")
        else:
            messagebox.showerror("Error", "Failed to create packet")

    def _on_send_burst(self) -> None:
        """Send 10 packets in rapid succession"""
        src = self.source_var.get()
        dst = self.dest_var.get()
        
        if not src or not dst:
            messagebox.showwarning("Warning", "Select source and destination")
            return
        
        src_id = src.split(":")[0]
        dst_id = dst.split(":")[0]
        
        count = 0
        for i in range(10):
            packet = self.network_manager.packet_manager.create_packet(
                src_id, dst_id,
                self.packet_size_var.get()
            )
            if packet:
                self.network_manager.packet_manager.start_packet_animation(packet)
                count += 1
        
        messagebox.showinfo("Success", f"{count} packets sent!")

    def _on_start_simulation(self) -> None:
        """Start/resume animation"""
        if hasattr(self.network_manager, 'packet_manager'):
            self.network_manager.animator_worker.resume()
            messagebox.showinfo("Info", "Simulation started")

    def _on_pause_simulation(self) -> None:
        """Pause animation"""
        if hasattr(self.network_manager, 'packet_manager'):
            self.network_manager.animator_worker.pause()
            messagebox.showinfo("Info", "Simulation paused")

    def _on_view_packet_metrics(self) -> None:
        """View metrics for latest delivered packet"""
        if not self.network_manager.packet_manager.delivered_packets:
            messagebox.showinfo("Info", "No delivered packets yet")
            return
        
        latest = self.network_manager.packet_manager.delivered_packets[-1]
        
        if hasattr(self.network_manager, 'main_window'):
            metrics = self.network_manager.main_window.latency_engine.get_packet_metrics(
                latest.id
            )
            if metrics:
                self.network_manager.main_window.metrics_display.update_packet_detail(latest.id)
                messagebox.showinfo("Packet Metrics",
                    f"Packet: {latest.id}\n"
                    f"Path: {' → '.join(metrics.path_nodes)}\n"
                    f"Actual Latency: {metrics.actual_latency:.2f}ms\n"
                    f"Theoretical Latency: {metrics.total_latency:.2f}ms\n"
                    f"Throughput: {metrics.throughput:.2f}Mbps\n"
                    f"Bottleneck BW: {metrics.bottleneck_bandwidth:.1f}Mbps")
                
    def _on_export_all(self) -> None:
        """Export all data"""
        results = self.network_manager.export_engine.export_all()
        
        success_count = sum(1 for v in results.values() if v)
        messagebox.showinfo("Export Complete",
            f"Files exported:\n"
            f"✓ Metrics: {results['metrics']}\n"
            f"✓ Congestion: {results['congestion']}\n"
            f"✓ Summary: {results['summary']}\n"
            f"✓ Topology: {results['topology']}\n\n"
            f"Check your CloudNetworkSimulator folder!")

    def _on_export_metrics(self) -> None:
        """Export metrics CSV"""
        if not self.network_manager.packet_manager.delivered_packets:
            messagebox.showwarning("Warning", "No delivered packets to export")
            return
        
        if self.network_manager.export_engine.export_metrics_to_csv():
            messagebox.showinfo("Success", "Metrics exported to CSV")
        else:
            messagebox.showerror("Error", "Failed to export metrics")

    def _on_export_congestion(self) -> None:
        """Export congestion CSV"""
        if self.network_manager.congestion_controller.get_queue_history():
            if self.network_manager.export_engine.export_congestion_to_csv():
                messagebox.showinfo("Success", "Congestion data exported to CSV")
            else:
                messagebox.showerror("Error", "Failed to export congestion data")
        else:
            messagebox.showwarning("Warning", "No congestion data to export")

    def _on_export_report(self) -> None:
        """Export report"""
        if self.network_manager.report_generator.generate_report():
            messagebox.showinfo("Success", "Report exported to TXT")
        else:
            messagebox.showerror("Error", "Failed to export report")

# ============================================================================
# 6. MAIN WINDOW
# ============================================================================

class MainWindow(tk.Tk):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        
        self.title(Config.WINDOW_TITLE)
        self.geometry(f"{Config.WINDOW_WIDTH}x{Config.WINDOW_HEIGHT}")
        
        self.network_manager = NetworkManager()
        
        # Initialize routing
        self.path_manager = PathManager(self.network_manager)
        self.network_manager.main_window = self
        
        # ← ADD THESE 3 BLOCKS (Stage 3)
        # Initialize animation worker (background thread for smooth animation)
        self.animator_worker = AnimatorWorker(
            update_callback=self._on_animation_update,
            frame_rate=30  # 30 FPS
        )
        self.animator_worker.start()  # Start background thread
        
        # Initialize latency/throughput engine (NEW IN STAGE 4)
        self.latency_engine = LatencyThroughputEngine(
            self.network_manager,
            self.animator_worker
        )

        # Initialize congestion controller (NEW IN STAGE 5)
        self.congestion_controller = CongestionController(
            self.network_manager,
            self.animator_worker
        )

        # Initialize export engine (NEW IN STAGE 6)
        self.export_engine = DataExportEngine(
            self.network_manager,
            self.latency_engine,
            self.congestion_controller
        )

        # Initialize report generator (NEW IN STAGE 6)
        self.report_generator = SimulationReportGenerator(
            self.network_manager,
            self.latency_engine,
            self.congestion_controller,
            self.animator_worker
        )

        # Initialize queue-aware packet manager (NEW IN STAGE 5)
        self.packet_manager = QueueAwarePacketManager(
            self.network_manager,
            self.path_manager,
            self.animator_worker,
            self.latency_engine,
            self.congestion_controller
        )
        self.network_manager.packet_manager = self.packet_manager
        
        self._create_layout()
        self._bind_events()
        
        # Display status
        self.status_label.config(text="✓ Ready. Click 'Add Node' button to start.")
        
        # ← ADD THIS LINE (cleanup on close)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def _create_layout(self) -> None:
        """Create main window layout"""
        
        # ========== MENU BAR ==========
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New", command=self._on_new)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._on_about)
        
        # ========== MAIN CONTAINER ==========
        main_container = tk.Frame(self)
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # ========== LEFT: CONTROL PANEL ==========
        left_frame = tk.Frame(main_container, bg="lightgray", relief=tk.SUNKEN, bd=1)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, 5))
        
        # Scrollable control panel
        canvas_scroll = tk.Canvas(left_frame, bg="lightgray", highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas_scroll.yview)
        scrollable_frame = tk.Frame(canvas_scroll, bg="lightgray")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        
        canvas_scroll.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas_scroll.configure(yscrollcommand=scrollbar.set)
        
        canvas_scroll.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.control_panel = ControlPanel(scrollable_frame, self.network_manager, 
                                        self.canvas_renderer, self._on_update)
        
        # ========== CENTER: CANVAS ==========
        center_frame = tk.Frame(main_container)
        center_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        tk.Label(center_frame, text="Network Topology", 
                font=("Arial", 11, "bold")).pack()
        
        self.canvas = tk.Canvas(center_frame, bg=Config.CANVAS_BG_COLOR,
                               width=Config.CANVAS_WIDTH, height=Config.CANVAS_HEIGHT,
                               relief=tk.SUNKEN, bd=2)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.canvas_renderer = CanvasRenderer(self.canvas, self.network_manager)
        self.control_panel.canvas_renderer = self.canvas_renderer
        
        # ========== BOTTOM: STATUS & METRICS ==========
        bottom_frame = tk.Frame(main_container, bg="lightyellow", relief=tk.SUNKEN, bd=1)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=(5, 0))

        tk.Label(bottom_frame, text="📊 Network Statistics", 
                font=("Arial", 10, "bold"), bg="lightyellow").pack(anchor="w", padx=10, pady=5)

        stats_frame = tk.Frame(bottom_frame, bg="lightyellow")
        stats_frame.pack(fill=tk.X, padx=10, pady=(0, 5))

        self.stats_label = tk.Label(stats_frame, text="", 
                                font=("Courier", 9), bg="lightyellow",
                                justify=tk.LEFT)
        self.stats_label.pack(anchor="w")

        # ========== METRICS PANEL (NEW IN STAGE 2) ==========
        metrics_frame = tk.Frame(bottom_frame, bg="lightcyan", 
                                relief=tk.SUNKEN, bd=1)
        metrics_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.metrics_label = tk.Label(metrics_frame, text="No path selected",
                                    font=("Courier", 9), bg="lightcyan",
                                    justify=tk.LEFT, padx=10, pady=10)
        self.metrics_label.pack(anchor="nw", fill=tk.BOTH, expand=True)

        self.metrics_display = EnhancedMetricsDisplay(
            self.metrics_label, 
            self.latency_engine
        )

        # ========== STATISTICS PANEL (NEW IN STAGE 4) ==========
        stats_frame = tk.Frame(bottom_frame, bg="lightgreen", 
                            relief=tk.SUNKEN, bd=1)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(stats_frame, text="📊 Real-time Statistics", 
                font=("Arial", 9, "bold"), bg="lightgreen").pack(anchor="w")

        self.stats_detailed_label = tk.Label(stats_frame, text="",
                                            font=("Courier", 8), bg="lightgreen",
                                            justify=tk.LEFT, padx=10, pady=5)
        self.stats_detailed_label.pack(anchor="nw", fill=tk.BOTH, expand=True)

        # ========== CONGESTION PANEL (NEW IN STAGE 5) ==========
        congestion_frame = tk.Frame(bottom_frame, bg="#FFE4E1",  # Light red
                                relief=tk.SUNKEN, bd=1)
        congestion_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tk.Label(congestion_frame, text="🔴 Congestion Control",
                font=("Arial", 9, "bold"), bg="#FFE4E1").pack(anchor="w")

        self.congestion_label = tk.Label(congestion_frame, text="",
                                        font=("Courier", 8), bg="#FFE4E1",
                                        justify=tk.LEFT, padx=10, pady=5)
        self.congestion_label.pack(anchor="nw", fill=tk.BOTH, expand=True)

        self.congestion_metrics_display = CongestionMetricsDisplay(
            self.congestion_label,
            self.congestion_controller,
            self.latency_engine
        )

        # Status bar
        status_frame = tk.Frame(self, relief=tk.SUNKEN, bd=1)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = tk.Label(status_frame, text="Ready", font=("Arial", 9))
        self.status_label.pack(anchor="w", padx=5, pady=2)
    
    def _bind_events(self) -> None:
        """Bind canvas and keyboard events"""
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.bind("<Delete>", self._on_delete_key)
    
    def _on_canvas_click(self, event) -> None:
        """Handle canvas click"""
        # Check if we're in "add node" mode
        if self.canvas.cget("cursor") == "crosshair":
            self._create_node_at(event.x, event.y)
            self.canvas.config(cursor="arrow")
            return
        
        # Check if clicked on node (for dragging)
        node = self.network_manager.get_node_by_pos(event.x, event.y)
        if node:
            self.canvas_renderer.dragged_node = node
            self.status_label.config(text=f"Dragging {node.label}...")
    
    def _on_canvas_drag(self, event) -> None:
        """Handle canvas drag"""
        if self.canvas_renderer.dragged_node:
            node = self.canvas_renderer.dragged_node
            
            # Keep within bounds
            x = max(node.radius, min(event.x, Config.CANVAS_WIDTH - node.radius))
            y = max(node.radius, min(event.y, Config.CANVAS_HEIGHT - node.radius))
            
            self.canvas_renderer.update_node_position(node.id, x, y)
    
    def _on_canvas_release(self, event) -> None:
        """Handle canvas release"""
        if self.canvas_renderer.dragged_node:
            node = self.canvas_renderer.dragged_node
            self.status_label.config(text=f"✓ {node.label} moved")
            self.canvas_renderer.dragged_node = None
            self._on_update()
    
    def _create_node_at(self, x: float, y: float) -> None:
        """Create a node at canvas coordinates"""
        try:
            label = self.control_panel.node_label_var.get() or None
            node = self.network_manager.add_node(x, y, label)
            self.canvas_renderer.draw_node(node)
            self.control_panel.update_node_list()
            self._on_update()
            self.status_label.config(text=f"✓ Node {node.id} created")
        except ValueError as e:
            messagebox.showwarning("Warning", str(e))
            self.status_label.config(text=f"✗ {str(e)}")
    
    def _on_delete_key(self, event) -> None:
        """Delete selected node (Delete key)"""
        if self.control_panel.source_var.get():
            self.control_panel._on_delete_node()
    
    def _on_update(self) -> None:
        """Called when topology changes"""
        self.network_manager.update_networkx_graph()
        self._update_statistics()

        # Track link metrics
        if hasattr(self, 'latency_engine'):
            for link in self.network_manager.links.values():
                if link.id not in self.latency_engine.link_metrics:
                    self.latency_engine.create_link_metrics(
                        link.id, link.node_a.id, link.node_b.id,
                        link.latency, link.bandwidth
                    )

        # Create queues for links
        if hasattr(self, 'congestion_controller'):
            for link in self.network_manager.links.values():
                if link.id not in self.congestion_controller.link_queues:
                    self.congestion_controller.create_link_queue(
                        link.id, link.queue_size,
                        drop_policy=DropPolicy.TAIL_DROP
                    )
    
    def _update_statistics(self) -> None:
        """Update network statistics display"""
        num_nodes = len(self.network_manager.nodes)
        num_links = len(self.network_manager.links)
        
        # Calculate total network properties
        total_latency = 0
        min_bandwidth = float('inf')
        
        if self.network_manager.links:
            for link in self.network_manager.links.values():
                total_latency += link.latency
                min_bandwidth = min(min_bandwidth, link.bandwidth)
        
        if min_bandwidth == float('inf'):
            min_bandwidth = 0
        
        stats_text = (
            f"Nodes: {num_nodes}  |  Links: {num_links}  |  "
            f"Total Latency: {total_latency:.1f}ms  |  "
            f"Min Bandwidth: {min_bandwidth:.1f}Mbps"
        )
        
        self.stats_label.config(text=stats_text)
    
    def _on_new(self) -> None:
        """Create new network"""
        if messagebox.askyesno("New Network", "Clear current network?"):
            self.network_manager.clear_all()
            self.canvas_renderer.redraw_all()
            self.control_panel.update_node_list()
            self._on_update()
            self.status_label.config(text="✓ New network created")
    
    def _on_about(self) -> None:
        """Show about dialog"""
        messagebox.showinfo("About Cloud Network Simulator",
            "Cloud Network Simulator v1.0\n\n"
            "A complete network simulation platform featuring:\n\n"
            "✓ Stage 1: Network Topology Editor\n"
            "✓ Stage 2: Dijkstra Routing\n"
            "✓ Stage 3: Packet Animation\n"
            "✓ Stage 4: Latency & Throughput\n"
            "✓ Stage 5: Congestion Control\n"
            "✓ Stage 6: Data Export & Reporting\n\n"
            "Features:\n"
            "• Interactive topology design\n"
            "• Smooth 30 FPS animation\n"
            "• Accurate latency calculations\n"
            "• Queue-based congestion\n"
            "• TCP-like flow control\n"
            "• Comprehensive data export\n\n"
            "© 2024 Cloud Network Simulator\n"
            "Educational Use Only")

    def update_metrics_display(self, path_info: PathInfo) -> None:
        """Update metrics display with path info"""
        if self.metrics_display:
            self.metrics_display.update_path_display(path_info)

    def _on_animation_update(self, active_packets: Dict, 
                            animators: Dict, sim_time: float) -> None:
        """Called from animator thread each frame"""
        packets_to_advance = []
        
        for pkt_id, animator in animators.items():
            # Check if animator finished this link
            if animator.update(sim_time):
                packets_to_advance.append(pkt_id)
        
        # Advance packets to next link (using main thread)
        if packets_to_advance:
            self.after(0, lambda: self._advance_packets(packets_to_advance))
        
        # Redraw canvas from main thread
        self.after(0, self._redraw_canvas_animation)

    def _advance_packets(self, packet_ids: List[str]) -> None:
        """Advance finished packets to next link"""
        for pkt_id in packet_ids:
            if pkt_id in self.packet_manager.active_packets:
                packet = self.packet_manager.active_packets[pkt_id]
                self.packet_manager.advance_packet(packet)

    def _redraw_canvas_animation(self) -> None:
        """Redraw canvas with animated packet positions"""
        # Redraw all links to show current congestion colors
        self.canvas_renderer.redraw_all()
        # Clear packet drawings (but keep topology)
        self.canvas.delete("packet")
        
        # Draw each active packet at its current position
        for pkt_id, animator in self.animator_worker.animators.items():
            pos = animator.get_current_position(self.animator_worker.sim_time)
            if pos:
                x, y = pos
                self.canvas.create_oval(
                    x - 5, y - 5, x + 5, y + 5,
                    fill="red", outline="darkred", width=2,
                    tags="packet"
                )
                # Draw packet ID
                self.canvas.create_text(
                    x, y - 10,
                    text=pkt_id,
                    font=("Arial", 7),
                    fill="red",
                    tags="packet"
                )

        self.update_statistics_display()
        # Update congestion display
        self.update_congestion_display()

    def on_closing(self) -> None:
        """Clean up when window closes"""
        if hasattr(self, 'animator_worker'):
            self.animator_worker.stop()
        self.destroy()

    def update_statistics_display(self) -> None:
        """Update statistics display"""
        if self.metrics_display:
            self.metrics_display.update_display()
        
        # Update detailed stats label
        stats = self.latency_engine.get_summary_statistics()
        stats_text = (
            f"Packets: {stats['total_sent']} sent | "
            f"{stats['total_delivered']} delivered | "
            f"{stats['total_dropped']} dropped | "
            f"Delivery Rate: {stats['delivery_rate']:.1f}% | "
            f"Avg Latency: {stats['avg_latency_ms']:.2f}ms | "
            f"Avg Throughput: {stats['avg_throughput_mbps']:.2f}Mbps"
        )
        self.stats_detailed_label.config(text=stats_text)

    def update_congestion_display(self) -> None:
        """Update congestion metrics display"""
        if hasattr(self, 'congestion_metrics_display'):
            self.congestion_metrics_display.update_display()

# ============================================================================
# 7. MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()