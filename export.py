import csv
import json
from datetime import datetime
from typing import Dict, List
import os

# ============================================================================
# 1. DATA EXPORT ENGINE
# ============================================================================

class DataExportEngine:
    """
    Exports all simulation data to various formats
    """
    
    def __init__(self, network_manager, latency_engine, congestion_controller):
        """
        Initialize export engine
        
        Args:
            network_manager: Reference to NetworkManager
            latency_engine: Reference to LatencyThroughputEngine
            congestion_controller: Reference to CongestionController
        """
        self.network_manager = network_manager
        self.latency_engine = latency_engine
        self.congestion_controller = congestion_controller
    
    def export_metrics_to_csv(self, filename: str = None) -> bool:
        """
        Export packet metrics to CSV
        
        Args:
            filename: Output filename (auto-generated if None)
        
        Returns:
            True if successful, False otherwise
        """
        if not filename:
            filename = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            metrics_dict = self.latency_engine.get_all_metrics()
            
            if not metrics_dict:
                return False
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow([
                    "Packet ID", "Source", "Destination", "Path",
                    "Size (bytes)", "Hops", "Theoretical Latency (ms)",
                    "Actual Latency (ms)", "Bottleneck BW (Mbps)",
                    "Throughput (Mbps)", "State", "Creation Time (ms)",
                    "Delivery Time (ms)"
                ])
                
                # Write packet data
                for metrics in sorted(metrics_dict.values(), 
                                     key=lambda x: x.packet_id):
                    writer.writerow([
                        metrics.packet_id,
                        metrics.source_node_id,
                        metrics.destination_node_id,
                        " → ".join(metrics.path_nodes),
                        metrics.packet_size,
                        metrics.hop_count,
                        f"{metrics.total_latency:.2f}",
                        f"{metrics.actual_latency:.2f}",
                        f"{metrics.bottleneck_bandwidth:.1f}",
                        f"{metrics.throughput:.2f}",
                        metrics.state,
                        f"{metrics.creation_time:.2f}",
                        f"{metrics.delivery_time:.2f}"
                    ])
            
            return True
        
        except Exception as e:
            print(f"Error exporting metrics: {e}")
            return False
    
    def export_congestion_to_csv(self, filename: str = None) -> bool:
        """
        Export congestion and queue statistics to CSV
        
        Args:
            filename: Output filename
        
        Returns:
            True if successful, False otherwise
        """
        if not filename:
            filename = f"congestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            queue_stats = self.congestion_controller.get_queue_history()
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow([
                    "Link ID", "Capacity", "Current Size", "Utilization (%)",
                    "Packets Enqueued", "Packets Dequeued", "Packets Dropped",
                    "Avg Delay (ms)"
                ])
                
                # Write link queue data
                for link_id, stats in queue_stats.items():
                    writer.writerow([
                        link_id,
                        stats['capacity'],
                        stats['current_size'],
                        f"{stats['utilization']*100:.1f}",
                        stats['packets_enqueued'],
                        stats['packets_dequeued'],
                        stats['packets_dropped'],
                        f"{stats['avg_delay_ms']:.2f}"
                    ])
            
            return True
        
        except Exception as e:
            print(f"Error exporting congestion data: {e}")
            return False
    
    def export_summary_to_csv(self, filename: str = None) -> bool:
        """
        Export overall simulation summary to CSV
        
        Args:
            filename: Output filename
        
        Returns:
            True if successful, False otherwise
        """
        if not filename:
            filename = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            latency_stats = self.latency_engine.get_summary_statistics()
            congestion_stats = self.congestion_controller.get_statistics()
            
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Write simulation summary
                writer.writerow(["SIMULATION SUMMARY"])
                writer.writerow([])
                
                writer.writerow(["Metric", "Value"])
                writer.writerow([])
                
                # Packet statistics
                writer.writerow(["PACKET STATISTICS"])
                writer.writerow(["Total Sent", latency_stats['total_sent']])
                writer.writerow(["Total Delivered", latency_stats['total_delivered']])
                writer.writerow(["Total Dropped", latency_stats['total_dropped']])
                writer.writerow(["Delivery Rate (%)", f"{latency_stats['delivery_rate']:.1f}"])
                writer.writerow(["Drop Rate (%)", f"{latency_stats['drop_rate']:.1f}"])
                writer.writerow([])
                
                # Latency statistics
                writer.writerow(["LATENCY STATISTICS (ms)"])
                writer.writerow(["Average", f"{latency_stats['avg_latency_ms']:.2f}"])
                writer.writerow(["Minimum", f"{latency_stats['min_latency_ms']:.2f}"])
                writer.writerow(["Maximum", f"{latency_stats['max_latency_ms']:.2f}"])
                writer.writerow([])
                
                # Throughput statistics
                writer.writerow(["THROUGHPUT STATISTICS (Mbps)"])
                writer.writerow(["Average", f"{latency_stats['avg_throughput_mbps']:.2f}"])
                writer.writerow([])
                
                # Congestion statistics
                writer.writerow(["CONGESTION STATISTICS"])
                writer.writerow(["Total Packets Enqueued", congestion_stats['total_enqueued']])
                writer.writerow(["Total Packets Dropped", congestion_stats['total_dropped']])
                writer.writerow(["Congestion Events", congestion_stats['congestion_events']])
                writer.writerow(["Avg Queue Depth", f"{congestion_stats['avg_queue_depth']:.1f}"])
                writer.writerow([])
                
                # Network topology
                writer.writerow(["TOPOLOGY"])
                writer.writerow(["Total Nodes", len(self.network_manager.nodes)])
                writer.writerow(["Total Links", len(self.network_manager.links)])
            
            return True
        
        except Exception as e:
            print(f"Error exporting summary: {e}")
            return False
    
    def export_topology_to_json(self, filename: str = None) -> bool:
        """
        Export network topology to JSON
        
        Args:
            filename: Output filename
        
        Returns:
            True if successful, False otherwise
        """
        if not filename:
            filename = f"topology_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            topology = {
                "timestamp": datetime.now().isoformat(),
                "nodes": [node.to_dict() for node in self.network_manager.nodes.values()],
                "links": [link.to_dict() for link in self.network_manager.links.values()],
            }
            
            with open(filename, 'w') as f:
                json.dump(topology, f, indent=2)
            
            return True
        
        except Exception as e:
            print(f"Error exporting topology: {e}")
            return False
    
    def export_all(self, base_filename: str = None) -> Dict[str, bool]:
        """
        Export all data to multiple formats
        
        Args:
            base_filename: Base name for files (timestamp added)
        
        Returns:
            Dictionary of filename -> success status
        """
        if not base_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_filename = f"simulation_{timestamp}"
        
        results = {}
        results['metrics'] = self.export_metrics_to_csv(f"{base_filename}_metrics.csv")
        results['congestion'] = self.export_congestion_to_csv(f"{base_filename}_congestion.csv")
        results['summary'] = self.export_summary_to_csv(f"{base_filename}_summary.csv")
        results['topology'] = self.export_topology_to_json(f"{base_filename}_topology.json")
        
        return results


# ============================================================================
# 2. SIMULATION REPORT GENERATOR
# ============================================================================

class SimulationReportGenerator:
    """
    Generates human-readable simulation reports
    """
    
    def __init__(self, network_manager, latency_engine, congestion_controller, animator_worker):
        """
        Initialize report generator
        
        Args:
            network_manager: Reference to NetworkManager
            latency_engine: Reference to LatencyThroughputEngine
            congestion_controller: Reference to CongestionController
            animator_worker: Reference to AnimatorWorker
        """
        self.network_manager = network_manager
        self.latency_engine = latency_engine
        self.congestion_controller = congestion_controller
        self.animator_worker = animator_worker
    
    def generate_report(self, filename: str = None) -> bool:
        """
        Generate comprehensive simulation report
        
        Args:
            filename: Output filename
        
        Returns:
            True if successful, False otherwise
        """
        if not filename:
            filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        try:
            with open(filename, 'w') as f:
                # Header
                f.write("=" * 70 + "\n")
                f.write("CLOUD NETWORK SIMULATOR - SIMULATION REPORT\n")
                f.write("=" * 70 + "\n\n")
                
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Simulation Time: {self.animator_worker.sim_time:.2f} ms\n\n")
                
                # Topology
                f.write("NETWORK TOPOLOGY\n")
                f.write("-" * 70 + "\n")
                f.write(f"Nodes: {len(self.network_manager.nodes)}\n")
                f.write(f"Links: {len(self.network_manager.links)}\n\n")
                
                # Node details
                f.write("Nodes:\n")
                for node_id, node in sorted(self.network_manager.nodes.items()):
                    f.write(f"  {node_id}: {node.label} at ({node.x:.0f}, {node.y:.0f})\n")
                f.write("\n")
                
                # Link details
                f.write("Links:\n")
                for link_id, link in sorted(self.network_manager.links.items()):
                    f.write(
                        f"  {link_id}: {link.node_a.label} ↔ {link.node_b.label}\n"
                        f"    Latency: {link.latency}ms | Bandwidth: {link.bandwidth}Mbps | Queue: {link.queue_size}\n"
                    )
                f.write("\n")
                
                # Latency Statistics
                latency_stats = self.latency_engine.get_summary_statistics()
                f.write("PACKET & LATENCY STATISTICS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total Packets Sent: {latency_stats['total_sent']}\n")
                f.write(f"Total Packets Delivered: {latency_stats['total_delivered']}\n")
                f.write(f"Total Packets Dropped: {latency_stats['total_dropped']}\n")
                f.write(f"Delivery Rate: {latency_stats['delivery_rate']:.1f}%\n")
                f.write(f"Drop Rate: {latency_stats['drop_rate']:.1f}%\n\n")
                
                f.write("Latency Metrics (ms):\n")
                f.write(f"  Average: {latency_stats['avg_latency_ms']:.2f}\n")
                f.write(f"  Minimum: {latency_stats['min_latency_ms']:.2f}\n")
                f.write(f"  Maximum: {latency_stats['max_latency_ms']:.2f}\n\n")
                
                f.write("Throughput:\n")
                f.write(f"  Average: {latency_stats['avg_throughput_mbps']:.2f} Mbps\n\n")
                
                # Congestion Statistics
                congestion_stats = self.congestion_controller.get_statistics()
                f.write("CONGESTION CONTROL STATISTICS\n")
                f.write("-" * 70 + "\n")
                f.write(f"Total Packets Enqueued: {congestion_stats['total_enqueued']}\n")
                f.write(f"Total Packets Dropped: {congestion_stats['total_dropped']}\n")
                f.write(f"Congestion Events: {congestion_stats['congestion_events']}\n")
                f.write(f"Average Queue Depth: {congestion_stats['avg_queue_depth']:.1f} packets\n\n")
                
                # Per-link queue statistics
                queue_stats = self.congestion_controller.get_queue_history()
                if queue_stats:
                    f.write("Per-Link Queue Statistics:\n")
                    for link_id, stats in queue_stats.items():
                        f.write(
                            f"  {link_id}:\n"
                            f"    Capacity: {stats['capacity']} packets\n"
                            f"    Current Size: {stats['current_size']} packets\n"
                            f"    Utilization: {stats['utilization']*100:.1f}%\n"
                            f"    Packets Enqueued: {stats['packets_enqueued']}\n"
                            f"    Packets Dequeued: {stats['packets_dequeued']}\n"
                            f"    Packets Dropped: {stats['packets_dropped']}\n"
                            f"    Avg Delay: {stats['avg_delay_ms']:.2f} ms\n\n"
                        )

                
                # Top packets by latency
                all_metrics = self.latency_engine.get_all_metrics()
                if all_metrics:
                    f.write("PACKET ANALYSIS\n")
                    f.write("-" * 70 + "\n")
                    
                    delivered = [m for m in all_metrics.values() if m.state == "delivered"]
                    if delivered:
                        f.write(f"Sample Packets (First 10 delivered):\n")
                        for pkt in sorted(delivered, key=lambda x: x.packet_id)[:10]:
                            f.write(
                                f"  {pkt.packet_id}: {pkt.source_node_id}→{pkt.destination_node_id}\n"
                                f"    Path: {' → '.join(pkt.path_nodes)}\n"
                                f"    Latency: {pkt.actual_latency:.2f}ms\n"
                                f"    Throughput: {pkt.throughput:.2f}Mbps\n\n"
                            )
                
                # Footer
                f.write("=" * 70 + "\n")
                f.write("END OF REPORT\n")
                f.write("=" * 70 + "\n")
            
            return True
        
        except Exception as e:
            print(f"Error generating report: {e}")
            return False

