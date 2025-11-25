import networkx as nx
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# ============================================================================
# 1. DIJKSTRA ROUTER
# ============================================================================

class DijkstraRouter:
    """
    Computes shortest paths using Dijkstra's algorithm via NetworkX
    """
    
    def __init__(self, graph: nx.Graph):
        """
        Initialize router with a NetworkX graph
        
        Args:
            graph: NetworkX Graph object
        """
        self.graph = graph
    
    def compute_shortest_path(self, start_node_id: str, end_node_id: str, 
                            metric: str = "latency") -> Optional[List[str]]:
        """
        Compute shortest path between two nodes using Dijkstra's algorithm
        
        Args:
            start_node_id: Starting node ID (e.g., "N1")
            end_node_id: Ending node ID (e.g., "N5")
            metric: "latency" (uses edge weight) or "hops" (unweighted)
        
        Returns:
            List of node IDs along path, or None if no path exists
        
        Example:
            path = router.compute_shortest_path("N1", "N5", metric="latency")
            # Returns: ["N1", "N3", "N4", "N5"]
        """
        
        # Validate nodes exist
        if start_node_id not in self.graph.nodes():
            raise ValueError(f"Start node {start_node_id} not in graph")
        if end_node_id not in self.graph.nodes():
            raise ValueError(f"End node {end_node_id} not in graph")
        
        # Same source and destination
        if start_node_id == end_node_id:
            raise ValueError("Source and destination must be different")
        
        try:
            if metric == "latency":
                # Use edge weights (latency) - Dijkstra finds minimum latency path
                path = nx.shortest_path(self.graph, 
                                       source=start_node_id,
                                       target=end_node_id,
                                       weight='weight')  # weight = latency
            elif metric == "hops":
                # Ignore weights - find path with fewest hops
                path = nx.shortest_path(self.graph,
                                       source=start_node_id,
                                       target=end_node_id)
            else:
                raise ValueError(f"Unknown metric: {metric}")
            
            return path
        
        except nx.NetworkXNoPath:
            # No path exists between nodes
            return None
    
    def get_path_cost(self, path: List[str]) -> float:
        """
        Calculate total latency cost of path (sum of all link latencies)
        
        Args:
            path: List of node IDs in path order
        
        Returns:
            Total latency in milliseconds
        
        Example:
            cost = router.get_path_cost(["N1", "N3", "N4", "N5"])
            # Returns: 15.0 (if links have latencies that sum to 15)
        """
        if len(path) < 2:
            return 0.0
        
        total_cost = 0.0
        
        # Sum up latencies between consecutive nodes
        for i in range(len(path) - 1):
            node_a = path[i]
            node_b = path[i + 1]
            
            # Get edge weight (latency)
            edge_data = self.graph.get_edge_data(node_a, node_b)
            if edge_data and 'weight' in edge_data:
                total_cost += edge_data['weight']
        
        return total_cost
    
    def get_bottleneck_bandwidth(self, path: List[str]) -> float:
        """
        Find minimum bandwidth along path (bottleneck)
        Throughput is limited by the slowest link
        
        Args:
            path: List of node IDs in path order
        
        Returns:
            Minimum bandwidth in Mbps
        
        Example:
            bw = router.get_bottleneck_bandwidth(["N1", "N3", "N4", "N5"])
            # Returns: 50.0 (the minimum bandwidth on any link)
        """
        if len(path) < 2:
            return 0.0
        
        min_bandwidth = float('inf')
        
        # Check bandwidth on all links in path
        for i in range(len(path) - 1):
            node_a = path[i]
            node_b = path[i + 1]
            
            edge_data = self.graph.get_edge_data(node_a, node_b)
            if edge_data and 'bandwidth' in edge_data:
                bandwidth = edge_data['bandwidth']
                min_bandwidth = min(min_bandwidth, bandwidth)
        
        if min_bandwidth == float('inf'):
            return 0.0
        
        return min_bandwidth
    
    def get_path_info(self, path: List[str], 
                     network_manager=None) -> Dict:
        """
        Get comprehensive path information
        
        Args:
            path: List of node IDs
            network_manager: Optional NetworkManager for accessing Link objects
        
        Returns:
            Dictionary with path details:
            {
                "path_nodes": ["N1", "N3", "N4", "N5"],
                "hop_count": 3,
                "total_latency": 15.0,
                "bottleneck_bandwidth": 50.0,
                "throughput": 50.0,
                "links": [Link, Link, Link],  # if network_manager provided
            }
        """
        if len(path) < 2:
            return {
                "path_nodes": path,
                "hop_count": 0,
                "total_latency": 0.0,
                "bottleneck_bandwidth": 0.0,
                "throughput": 0.0,
                "links": []
            }
        
        total_latency = self.get_path_cost(path)
        bottleneck_bw = self.get_bottleneck_bandwidth(path)
        hop_count = len(path) - 1  # Number of hops = edges = nodes - 1
        
        # Gather Link objects if network_manager provided
        links = []
        if network_manager:
            for i in range(len(path) - 1):
                link = network_manager.get_link_by_nodes(path[i], path[i + 1])
                if link:
                    links.append(link)
        
        return {
            "path_nodes": path,
            "hop_count": hop_count,
            "total_latency": total_latency,
            "bottleneck_bandwidth": bottleneck_bw,
            "throughput": bottleneck_bw,  # Throughput = bottleneck bandwidth
            "links": links,
        }


# ============================================================================
# 2. PATH MANAGER
# ============================================================================

@dataclass
class PathInfo:
    """Data class for storing path information"""
    source_id: str
    destination_id: str
    path_nodes: List[str]
    hop_count: int
    total_latency: float
    bottleneck_bandwidth: float
    throughput: float
    links: List = field(default_factory=list)
    timestamp: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "source_id": self.source_id,
            "destination_id": self.destination_id,
            "path_nodes": self.path_nodes,
            "hop_count": self.hop_count,
            "total_latency": self.total_latency,
            "bottleneck_bandwidth": self.bottleneck_bandwidth,
            "throughput": self.throughput,
        }


class PathManager:
    """
    Manages path computation and storage
    """
    
    def __init__(self, network_manager):
        """
        Initialize PathManager
        
        Args:
            network_manager: Reference to NetworkManager instance
        """
        self.network_manager = network_manager
        self.router = DijkstraRouter(network_manager.graph)
        self.current_path: Optional[PathInfo] = None
        self.path_history: List[PathInfo] = []
    
    def set_path(self, source_id: str, dest_id: str) -> bool:
        """
        Compute and set current path using Dijkstra
        
        Args:
            source_id: Source node ID
            dest_id: Destination node ID
        
        Returns:
            True if path found, False otherwise
        """
        try:
            # Update router with latest graph
            self.router.graph = self.network_manager.graph
            
            # Compute shortest path
            path_nodes = self.router.compute_shortest_path(
                source_id, dest_id, metric="latency"
            )
            
            if path_nodes is None:
                self.current_path = None
                return False
            
            # Get detailed path information
            path_dict = self.router.get_path_info(
                path_nodes, 
                self.network_manager
            )
            
            # Create PathInfo object
            self.current_path = PathInfo(
                source_id=source_id,
                destination_id=dest_id,
                path_nodes=path_nodes,
                hop_count=path_dict["hop_count"],
                total_latency=path_dict["total_latency"],
                bottleneck_bandwidth=path_dict["bottleneck_bandwidth"],
                throughput=path_dict["throughput"],
                links=path_dict["links"]
            )
            
            # Add to history
            self.path_history.append(self.current_path)
            
            return True
        
        except (ValueError, nx.NetworkXError) as e:
            print(f"Path computation error: {e}")
            self.current_path = None
            return False
    
    def get_current_path(self) -> Optional[PathInfo]:
        """Get current path object"""
        return self.current_path
    
    def get_current_path_nodes(self) -> Optional[List[str]]:
        """Get current path as list of node IDs"""
        if self.current_path:
            return self.current_path.path_nodes
        return None
    
    def get_path_info(self) -> Optional[dict]:
        """Get current path info as dictionary"""
        if self.current_path:
            return self.current_path.to_dict()
        return None
    
    def get_path_links(self) -> Optional[List]:
        """Get list of Link objects in current path"""
        if self.current_path:
            return self.current_path.links
        return None
    
    def clear_path(self) -> None:
        """Clear current path"""
        self.current_path = None
    
    def get_history(self) -> List[PathInfo]:
        """Get all computed paths in history"""
        return self.path_history


# ============================================================================
# 3. METRICS DISPLAY (Updated for Stage 2)
# ============================================================================

class MetricsDisplay:
    """
    Displays network metrics in the UI
    """
    
    def __init__(self, label_widget):
        """
        Initialize metrics display
        
        Args:
            label_widget: Tkinter Label widget to display metrics in
        """
        self.label = label_widget
        self.current_path_info = None
    
    def update_path_display(self, path_info: Optional[PathInfo]) -> None:
        """
        Update display with path information
        
        Args:
            path_info: PathInfo object or None
        """
        self.current_path_info = path_info
        self._refresh_display()
    
    def _refresh_display(self) -> None:
        """Refresh the metrics display"""
        if not self.current_path_info:
            self.label.config(text="No path selected")
            return
        
        info = self.current_path_info
        
        # Format path nodes nicely
        path_str = " → ".join(info.path_nodes)
        
        display_text = (
            f"═══════════════════════════════════════════\n"
            f"📍 CURRENT PATH\n"
            f"═══════════════════════════════════════════\n"
            f"Path: {path_str}\n"
            f"Hops: {info.hop_count}\n\n"
            f"═══════════════════════════════════════════\n"
            f"📊 PATH METRICS\n"
            f"═══════════════════════════════════════════\n"
            f"Total Latency:        {info.total_latency:.2f} ms\n"
            f"Bottleneck BW:        {info.bottleneck_bandwidth:.1f} Mbps\n"
            f"Throughput:           {info.throughput:.1f} Mbps\n"
            f"═══════════════════════════════════════════"
        )
        
        self.label.config(text=display_text)

