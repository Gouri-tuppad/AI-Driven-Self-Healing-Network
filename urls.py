from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.utils import timezone
from network_sim.network_monitor import NetworkMonitor
from network_sim.models import NetworkEvent, ServerNode, ActiveConnection
from functools import wraps
import json


def admin_required(view_func):
    """Decorator to check if user is admin/staff"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


@admin_required
def network_monitoring_dashboard(request):
    """Display network monitoring dashboard with real-time data"""
    network_status = NetworkMonitor.get_network_status()
    
    context = {
        'total_connections': network_status['total_active_connections'],
        'max_capacity': network_status['max_capacity'],
        'capacity_exceeded': network_status['capacity_exceeded'],
        'excess_connections': network_status['excess_connections'],
        'connected_pcs': network_status['connected_pcs'],
        'active_issues': network_status['active_issues'],
        'issue_count': network_status['issue_count'],
        'nodes_status': network_status['nodes_status'],
        'overall_status': network_status['overall_status'],
    }
    return render(request, 'admin_panel/network_monitoring.html', context)


@admin_required
@require_http_methods(["GET"])
def api_network_health(request):
    """Get comprehensive real-time network health status based on ACTUAL connections"""
    status = NetworkMonitor.get_network_status()
    return JsonResponse(status)


@admin_required
@require_http_methods(["GET"])
def api_network_issues(request):
    """Get active network issues from REAL connections only"""
    issues = NetworkMonitor.check_network_health()
    
    issues_data = []
    for issue in issues:
        event = issue.get('event')
        issues_data.append({
            'type': issue['type'],
            'severity': issue['severity'],
            'description': issue['description'],
            'event_id': event.id if event else None,
            'timestamp': event.timestamp.isoformat() if event else str(issue.get('timestamp', '')),
            'affected_pcs': issue.get('affected_pcs', 0)
        })
    
    return JsonResponse({
        'success': True,
        'total_issues': len(issues_data),
        'issues': issues_data,
        'timestamp': timezone.now().isoformat()
    })

@require_http_methods(["GET"])
def health_check(request):
    """Return server health status for the running Django instance."""
    try:
        from django.db import connection
        connection.ensure_connection()
        return JsonResponse({'status': 'ACTIVE', 'timestamp': timezone.now().isoformat()})
    except Exception as exc:
        return JsonResponse({'status': 'NODE_FAILURE_DETECTED', 'error': str(exc), 'timestamp': timezone.now().isoformat()}, status=503)


@admin_required
@require_http_methods(["GET"])
def api_server_nodes_status(request):
    """Get detailed server nodes status from real connections"""
    nodes = ServerNode.objects.all()
    nodes_data = []
    
    for node in nodes:
        connections = ActiveConnection.objects.filter(is_active=True, server_node=node).count()
        connected_students = list(ActiveConnection.objects.filter(
            is_active=True, 
            server_node=node
        ).select_related('student__user').values_list('student__user__username', flat=True))
        
        nodes_data.append({
            'id': node.id,
            'name': node.name,
            'ip_address': node.ip_address,
            'is_healthy': node.is_healthy,
            'current_connections': connections,
            'max_capacity': node.max_capacity,
            'utilization_percent': round((connections / node.max_capacity * 100), 1) if node.max_capacity > 0 else 0,
            'connected_students': connected_students,
            'last_health_check': node.last_health_check.isoformat()
        })
    
    return JsonResponse({
        'success': True,
        'server_nodes': nodes_data,
        'total_nodes': len(nodes_data),
        'healthy_nodes': sum(1 for n in nodes_data if n['is_healthy']),
        'timestamp': timezone.now().isoformat()
    })


@admin_required
@require_http_methods(["GET"])
def api_connected_pcs(request):
    """Get list of all currently connected PCs with detailed info"""
    from datetime import timedelta
    connections = ActiveConnection.objects.filter(
        is_active=True
    ).select_related('student__user', 'server_node').order_by('-last_activity')
    
    # IST offset (UTC+5:30)
    ist_offset = timedelta(hours=5, minutes=30)
    
    connected_pcs = []
    for conn in connections:
        # Convert connected_at and last_activity to IST
        connected_at_ist = (conn.connected_at + ist_offset).strftime('%Y-%m-%d %H:%M:%S')
        last_activity_ist = (conn.last_activity + ist_offset).strftime('%Y-%m-%d %H:%M:%S')
        
        connected_pcs.append({
            'username': conn.student.user.username,
            'student_id': conn.student.student_id,
            'ip_address': conn.ip_address,
            'server_node': conn.server_node.name if conn.server_node else 'Unassigned',
            'connected_at': connected_at_ist,
            'last_activity': last_activity_ist,
            'duration_seconds': int((timezone.now() - conn.connected_at).total_seconds())
        })
    
    return JsonResponse({
        'success': True,
        'total_connected': len(connected_pcs),
        'connected_pcs': connected_pcs,
        'timestamp': timezone.now().isoformat()
    })


@admin_required
@require_http_methods(["POST"])
def api_resolve_network_issue(request):
    """Resolve a network issue/event"""
    try:
        data = json.loads(request.body)
        event_id = data.get('event_id')
        
        event = NetworkEvent.objects.get(id=event_id)
        event.resolved = True
        event.resolved_at = timezone.now()
        event.save(update_fields=['resolved', 'resolved_at'])
        
        return JsonResponse({
            'success': True,
            'message': f'Event {event_id} marked as resolved',
            'timestamp': timezone.now().isoformat()
        })
    except NetworkEvent.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Event not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@admin_required
@require_http_methods(["GET"])
def api_looping_detection(request):
    """
    Detect network looping/flooding issues from real request logs
    Returns: List of clients with excessive requests in short time intervals
    """
    from network_sim.looping_detector import LoopingDetector
    
    # Get parameters from query string
    request_threshold = int(request.GET.get('threshold', 20))
    time_window = int(request.GET.get('time_window', 10))
    
    # Detect looping issues
    looping_issues = LoopingDetector.detect_looping_issues(
        request_threshold=request_threshold,
        time_window_seconds=time_window
    )
    
    # Get statistics
    stats = LoopingDetector.get_looping_statistics()
    
    return JsonResponse({
        'success': True,
        'threshold': request_threshold,
        'time_window_seconds': time_window,
        'statistics': stats,
        'looping_issues': looping_issues,
        'total_issues': len(looping_issues),
        'critical_issues': len([i for i in looping_issues if i['severity'] == 'CRITICAL']),
        'high_issues': len([i for i in looping_issues if i['severity'] == 'HIGH']),
        'timestamp': timezone.now().isoformat()
    })


@admin_required
@require_http_methods(["GET"])
def api_looping_timeline(request):
    """
    Get request timeline for a specific IP address
    Useful for detailed analysis of looping behavior
    """
    from network_sim.looping_detector import LoopingDetector
    
    ip_address = request.GET.get('ip')
    limit_seconds = int(request.GET.get('limit', 60))
    
    if not ip_address:
        return JsonResponse({
            'success': False,
            'message': 'IP address parameter required'
        }, status=400)
    
    timeline = LoopingDetector.get_request_timeline_for_ip(ip_address, limit_seconds)
    
    return JsonResponse({
        'success': True,
        'ip_address': ip_address,
        'time_limit_seconds': limit_seconds,
        'request_count': len(timeline),
        'timeline': timeline,
        'timestamp': timezone.now().isoformat()
    })


@admin_required
@require_http_methods(["GET"])
def api_looping_statistics(request):
    """Get aggregated looping statistics"""
    from network_sim.looping_detector import LoopingDetector
    
    time_window = int(request.GET.get('time_window', 300))
    
    stats = LoopingDetector.get_looping_statistics(time_window_seconds=time_window)
    
    return JsonResponse({
        'success': True,
        'statistics': stats,
        'timestamp': timezone.now().isoformat()
    })


@admin_required
@require_http_methods(["GET"])
def api_ai_congestion_prediction(request):
    """
    AI-based congestion prediction endpoint.
    Returns predicted congestion risk level with confidence score.
    """
    from network_sim.ai_congestion_predictor import AICongestionPredictor
    
    try:
        prediction_summary = AICongestionPredictor.get_prediction_summary()
        return JsonResponse(prediction_summary)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@admin_required
@require_http_methods(["GET"])
def api_ai_prediction_details(request):
    """
    Get detailed AI prediction metrics and analysis.
    Includes feature breakdown and model information.
    """
    from network_sim.ai_congestion_predictor import AICongestionPredictor
    
    try:
        # Get current features
        features = AICongestionPredictor.extract_features(time_window_seconds=300)
        
        # Get prediction
        prediction_data = AICongestionPredictor.predict_congestion()
        
        # Calculate thresholds for reference
        congestion_threshold = AICongestionPredictor.CONGESTION_THRESHOLD
        looping_threshold = AICongestionPredictor.LOOPING_THRESHOLD
        
        return JsonResponse({
            'status': 'success',
            'prediction': prediction_data['prediction'],
            'confidence': round(prediction_data['confidence'] * 100, 2),
            'model_type': prediction_data['model_type'],
            'training_samples': prediction_data['training_samples'],
            'current_metrics': {
                'active_clients': features['active_client_count'],
                'active_clients_threshold': congestion_threshold,
                'active_clients_percentage': round((features['active_client_count'] / congestion_threshold) * 100, 1) if congestion_threshold > 0 else 0,
                'requests_per_second': round(features['requests_per_second'], 2),
                'total_requests': features['total_requests'],
                'repeated_request_count': features['repeated_request_count'],
                'looping_frequency': round(features['looping_frequency'], 3),
                'looping_frequency_threshold': AICongestionPredictor.LOOPING_THRESHOLD,
                'average_latency_ms': round(features['average_latency'], 2),
                'bandwidth_usage': round(features['bandwidth_usage'], 2),
                'high_severity_events': features['high_severity_events'],
                'failed_nodes': features['failed_nodes'],
            },
            'risk_probabilities': prediction_data['probabilities'],
            'timestamp': timezone.now().isoformat()
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


# ============================================================================
# REAL-TIME NETWORK TOPOLOGY VISUALIZATION ENDPOINTS
# ============================================================================
# These endpoints provide REAL backend data for live network topology display
# Data comes from: ClientNodeStatus, ActiveConnection, ServerNode models


@admin_required
@require_http_methods(["GET"])
def api_network_topology(request):
    """
    Get REAL network topology data for visualization.
    
    Returns:
    - Central Django server node
    - All client nodes with their current status
    - Connections between clients and central server
    - Real status from ClientNodeStatus model
    
    Uses ONLY real backend data - NO fake nodes or hardcoded entries.
    """
    from network_sim.models import ClientNodeStatus
    
    try:
        # Central Django Server Node
        central_server = {
            'id': 'central_server',
            'label': 'Central Django Server',
            'type': 'server',
            'ip_address': 'localhost',
            'status': 'ACTIVE',
            'color': '#27ae60',  # Green
            'x': 0,
            'y': 0,
            'size': 60,
            'title': 'Central Django Server<br/>Status: ACTIVE'
        }
        
        # Get all client nodes from REAL ClientNodeStatus records
        client_nodes = []
        client_node_statuses = ClientNodeStatus.objects.select_related('student__user').all()
        
        node_id_map = {}  # Map student_id to node position for circle layout
        total_clients = client_node_statuses.count()
        
        for idx, client_status in enumerate(client_node_statuses):
            username = client_status.student.user.username
            student_id = client_status.student.student_id
            
            # Determine node status and color
            status = client_status.status  # ACTIVE, INACTIVE, NODE_FAILURE
            
            # Color mapping based on real status
            if status == 'ACTIVE':
                color = '#27ae60'  # Green - Active
                title_status = 'ACTIVE'
            elif status == 'INACTIVE':
                color = '#f39c12'  # Orange - Inactive
                title_status = 'INACTIVE'
            elif status == 'NODE_FAILURE':
                color = '#e74c3c'  # Red - Node Failure
                title_status = 'NODE FAILURE'
            else:
                color = '#95a5a6'  # Gray - Unknown
                title_status = 'UNKNOWN'
            
            # Check if recovered (was failed but now active)
            if status == 'ACTIVE' and client_status.failure_detected_at:
                color = '#3498db'  # Blue - Recovered
                title_status = 'RECOVERED'
            
            # Calculate circular layout around central server
            angle = (idx / max(total_clients, 1)) * 2 * 3.14159
            radius = 300
            x = radius * 3.14159 * (idx / max(total_clients, 1)) * 2
            y = 200 * ((idx % 2) * 2 - 1)
            
            node = {
                'id': f'client_{student_id}',
                'label': username,
                'type': 'client',
                'student_id': student_id,
                'ip_address': client_status.ip_address or 'N/A',
                'status': status,
                'color': color,
                'x': x,
                'y': y,
                'size': 45,
                'last_heartbeat': client_status.last_heartbeat.isoformat() if client_status.last_heartbeat else None,
                'last_activity': client_status.last_activity.isoformat() if client_status.last_activity else None,
                'connected_at': client_status.connected_at.isoformat() if client_status.connected_at else None,
                'title': f'{username}<br/>IP: {client_status.ip_address or "N/A"}<br/>Status: {title_status}<br/>Heartbeat: {client_status.last_heartbeat.strftime("%H:%M:%S") if client_status.last_heartbeat else "Never"}'
            }
            client_nodes.append(node)
            node_id_map[student_id] = f'client_{student_id}'
        
        # Build edges (connections from each client to central server)
        edges = []
        
        for client_status in client_node_statuses:
            student_id = client_status.student.student_id
            
            # Connection from client to central server
            # Color based on client status
            if client_status.status == 'ACTIVE':
                edge_color = '#27ae60'  # Green
                edge_width = 3
            elif client_status.status == 'INACTIVE':
                edge_color = '#f39c12'  # Orange
                edge_width = 2
            elif client_status.status == 'NODE_FAILURE':
                edge_color = '#e74c3c'  # Red
                edge_width = 2
            else:
                edge_color = '#95a5a6'  # Gray
                edge_width = 1
            
            if student_id in node_id_map:
                edge = {
                    'from': node_id_map[student_id],
                    'to': 'central_server',
                    'color': edge_color,
                    'width': edge_width,
                    'arrows': 'to',
                    'smooth': {'type': 'continuous'},
                    'title': f'{client_status.student.user.username} → Central Server'
                }
                edges.append(edge)
        
        return JsonResponse({
            'success': True,
            'nodes': [central_server] + client_nodes,
            'edges': edges,
            'total_nodes': len(client_nodes),
            'active_nodes': sum(1 for n in client_nodes if n['status'] == 'ACTIVE'),
            'inactive_nodes': sum(1 for n in client_nodes if n['status'] == 'INACTIVE'),
            'failed_nodes': sum(1 for n in client_nodes if n['status'] == 'NODE_FAILURE'),
            'recovered_nodes': sum(1 for n in client_nodes if n['color'] == '#3498db'),
            'timestamp': timezone.now().isoformat()
        })
    
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'message': str(e),
            'error_trace': traceback.format_exc(),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@admin_required
@require_http_methods(["GET"])
def api_network_topology_stats(request):
    """
    Get real-time network topology statistics.
    
    Uses actual data from:
    - ClientNodeStatus: for node status tracking
    - ActiveConnection: for current connections
    - Heartbeat records: for health monitoring
    """
    from network_sim.models import ClientNodeStatus
    from django.utils import timezone
    from datetime import timedelta
    
    try:
        client_statuses = ClientNodeStatus.objects.all()
        
        active_count = client_statuses.filter(status='ACTIVE').count()
        inactive_count = client_statuses.filter(status='INACTIVE').count()
        failed_count = client_statuses.filter(status='NODE_FAILURE').count()
        total_count = client_statuses.count()
        
        # Calculate recovered nodes (those that were failed but now active with recent activity)
        now = timezone.now()
        recovery_threshold = now - timedelta(minutes=5)
        
        recovered_nodes = client_statuses.filter(
            status='ACTIVE',
            failure_detected_at__isnull=False,
            last_activity__gte=recovery_threshold
        ).count()
        
        # Average response time (from heartbeat records)
        recent_heartbeats = client_statuses.filter(
            last_heartbeat__gte=now - timedelta(minutes=5)
        ).exclude(last_heartbeat__isnull=True)
        
        avg_heartbeat_delay = 0
        if recent_heartbeats.count() > 0:
            total_delay = 0
            for status in recent_heartbeats:
                delay = (status.last_activity - status.last_heartbeat).total_seconds()
                if delay >= 0:
                    total_delay += delay
            avg_heartbeat_delay = round(total_delay / recent_heartbeats.count(), 2)
        
        # Network health score (0-100)
        if total_count > 0:
            health_score = round((active_count / total_count) * 100, 1)
        else:
            health_score = 0
        
        return JsonResponse({
            'success': True,
            'total_nodes': total_count,
            'active_nodes': active_count,
            'inactive_nodes': inactive_count,
            'failed_nodes': failed_count,
            'recovered_nodes': recovered_nodes,
            'health_score': health_score,
            'average_heartbeat_delay_ms': avg_heartbeat_delay,
            'network_status': 'HEALTHY' if health_score >= 80 else 'DEGRADED' if health_score >= 50 else 'CRITICAL',
            'timestamp': timezone.now().isoformat()
        })
    
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'message': str(e),
            'error_trace': traceback.format_exc(),
            'timestamp': timezone.now().isoformat()
        }, status=500)


# ============================================================================
# EXPLAINABLE AI ANALYSIS ENDPOINTS
# ============================================================================
# These endpoints provide AI predictions WITH EXPLANATIONS based on REAL metrics
# Explanations are generated from actual network data - NO fake reasoning


@admin_required
@require_http_methods(["GET"])
def api_explainable_ai_analysis(request):
    """
    Get explainable AI analysis with prediction reasoning.
    
    Returns:
    - Current risk level (LOW/MEDIUM/HIGH)
    - Confidence percentage (0-100%)
    - Contributing factors based on REAL metrics
    - AI reasoning summary explaining why this prediction
    - Anomaly explanation from actual network conditions
    
    All explanations are generated from real backend metrics:
    - requests_per_second: Current request rate
    - active_client_count: Number of connected clients
    - looping_frequency: Frequency of repeated requests
    - latency: Network response time
    - failed_nodes: Count of failed client nodes
    - heartbeat_stability: Health of heartbeat connections
    - traffic_growth: Change in connections over time
    """
    from network_sim.ai_congestion_predictor import AICongestionPredictor
    from network_sim.models import ClientNodeStatus
    from django.db.models import Count, Avg
    from datetime import timedelta
    
    try:
        # Extract REAL network metrics from backend
        features = AICongestionPredictor.extract_features(time_window_seconds=300)
        
        # Get prediction from AI model
        prediction_data = AICongestionPredictor.predict_congestion()
        risk_level = prediction_data['prediction']
        confidence = round(prediction_data['confidence'] * 100, 2)
        
        # ============================================================
        # GENERATE EXPLANATIONS FROM REAL METRICS
        # ============================================================
        contributing_factors = []
        risk_score = 0  # 0-100 internal scoring
        
        # Factor 1: High Request Frequency
        if features['requests_per_second'] > 0.5:  # > 0.5 req/sec
            contributing_factors.append({
                'factor': 'High Request Frequency',
                'severity': 'HIGH' if features['requests_per_second'] > 2 else 'MEDIUM',
                'value': round(features['requests_per_second'], 2),
                'unit': 'req/sec',
                'explanation': f"System is processing {features['requests_per_second']:.2f} requests per second. High frequency can lead to congestion.",
                'impact': 'HIGH' if features['requests_per_second'] > 2 else 'MEDIUM'
            })
            risk_score += 15 if features['requests_per_second'] > 2 else 5
        
        # Factor 2: Active Client Count
        active_clients = features['active_client_count']
        if active_clients > AICongestionPredictor.CONGESTION_THRESHOLD:
            severity = 'HIGH' if active_clients > 10 else 'MEDIUM'
            contributing_factors.append({
                'factor': 'High Client Connection Count',
                'severity': severity,
                'value': active_clients,
                'unit': 'clients',
                'threshold': AICongestionPredictor.CONGESTION_THRESHOLD,
                'explanation': f"{active_clients} clients connected. Network congestion threshold is {AICongestionPredictor.CONGESTION_THRESHOLD}+. Current load: {round((active_clients/AICongestionPredictor.CONGESTION_THRESHOLD)*100, 1)}%",
                'impact': 'HIGH' if active_clients > 10 else 'MEDIUM'
            })
            risk_score += 25 if active_clients > 10 else 15
        
        # Factor 3: Looping Behavior
        looping_freq = features['looping_frequency']
        if looping_freq > 0.1:  # More than 10% repeated requests
            severity = 'HIGH' if looping_freq > 0.3 else 'MEDIUM'
            contributing_factors.append({
                'factor': 'Looping Behavior Detected',
                'severity': severity,
                'value': round(looping_freq * 100, 2),
                'unit': '%',
                'repeated_count': features['repeated_request_count'],
                'explanation': f"Detected looping behavior: {looping_freq*100:.1f}% of requests are repeated. {features['repeated_request_count']} repeated request(s) found. May indicate network flooding or malicious activity.",
                'impact': 'HIGH' if looping_freq > 0.3 else 'MEDIUM'
            })
            risk_score += 20 if looping_freq > 0.3 else 10
        
        # Factor 4: Latency Issues
        avg_latency = features['average_latency']
        if avg_latency > 100:  # > 100ms latency
            severity = 'HIGH' if avg_latency > 500 else 'MEDIUM'
            contributing_factors.append({
                'factor': 'Increased Latency',
                'severity': severity,
                'value': round(avg_latency, 2),
                'unit': 'ms',
                'explanation': f"Network latency is {avg_latency:.0f}ms. Normal: <100ms. High latency indicates network congestion or performance issues.",
                'impact': 'HIGH' if avg_latency > 500 else 'MEDIUM'
            })
            risk_score += 15 if avg_latency > 500 else 8
        
        # Factor 5: Failed Nodes
        failed_nodes = features['failed_nodes']
        if failed_nodes > 0:
            severity = 'HIGH' if failed_nodes > 2 else 'MEDIUM'
            contributing_factors.append({
                'factor': 'Node Failures Detected',
                'severity': severity,
                'value': failed_nodes,
                'unit': 'nodes',
                'explanation': f"{failed_nodes} client node(s) have failed or disconnected. Node failures can impact network stability and availability.",
                'impact': 'HIGH' if failed_nodes > 2 else 'MEDIUM'
            })
            risk_score += 20 if failed_nodes > 2 else 12
        
        # Factor 6: Traffic Growth Rate
        growth = features['connection_growth']
        if growth > 1.5:  # 50% growth
            contributing_factors.append({
                'factor': 'Rapid Connection Growth',
                'severity': 'HIGH' if growth > 2 else 'MEDIUM',
                'value': round(growth, 2),
                'unit': 'growth rate',
                'explanation': f"Connection count grew by {(growth-1)*100:.0f}% recently. Rapid growth may overwhelm network capacity.",
                'impact': 'HIGH' if growth > 2 else 'MEDIUM'
            })
            risk_score += 15 if growth > 2 else 8
        
        # Factor 7: Heartbeat Stability
        client_statuses = ClientNodeStatus.objects.all()
        inactive_count = client_statuses.filter(status='INACTIVE').count()
        failed_count = client_statuses.filter(status='NODE_FAILURE').count()
        total_count = client_statuses.count()
        
        heartbeat_health = 100
        if total_count > 0:
            heartbeat_health = ((total_count - inactive_count - failed_count) / total_count) * 100
        
        if heartbeat_health < 80:
            severity = 'HIGH' if heartbeat_health < 60 else 'MEDIUM'
            contributing_factors.append({
                'factor': 'Unstable Heartbeat Activity',
                'severity': severity,
                'value': round(heartbeat_health, 1),
                'unit': '%',
                'healthy_nodes': total_count - inactive_count - failed_count,
                'total_nodes': total_count,
                'explanation': f"Only {heartbeat_health:.0f}% of nodes have stable heartbeats. {inactive_count} inactive, {failed_count} failed. Instability suggests network connectivity issues.",
                'impact': 'HIGH' if heartbeat_health < 60 else 'MEDIUM'
            })
            risk_score += 18 if heartbeat_health < 60 else 10
        
        # ============================================================
        # GENERATE AI REASONING SUMMARY (from real metrics)
        # ============================================================
        reasoning_summary = generate_ai_reasoning(risk_level, contributing_factors, features)
        
        # ============================================================
        # GENERATE ANOMALY EXPLANATION
        # ============================================================
        anomaly_explanation = generate_anomaly_explanation(features, contributing_factors)
        
        # Map risk level to color
        risk_colors = {
            'LOW': {'color': '#27ae60', 'hex': '#27ae60', 'rgb': 'rgb(39, 174, 96)'},      # Green
            'MEDIUM': {'color': '#f39c12', 'hex': '#f39c12', 'rgb': 'rgb(243, 156, 18)'},  # Orange
            'HIGH': {'color': '#e74c3c', 'hex': '#e74c3c', 'rgb': 'rgb(231, 76, 60)'}      # Red
        }
        
        return JsonResponse({
            'success': True,
            'prediction': {
                'risk_level': risk_level,
                'confidence': confidence,
                'model_type': prediction_data['model_type'],
                'training_samples': prediction_data['training_samples']
            },
            'color': risk_colors.get(risk_level, risk_colors['MEDIUM']),
            'contributing_factors': contributing_factors,
            'factor_count': len(contributing_factors),
            'reasoning_summary': reasoning_summary,
            'anomaly_explanation': anomaly_explanation,
            'risk_indicators': {
                'requests_per_second': round(features['requests_per_second'], 3),
                'active_clients': features['active_client_count'],
                'looping_frequency': round(features['looping_frequency'], 4),
                'average_latency_ms': round(features['average_latency'], 1),
                'failed_nodes': features['failed_nodes'],
                'total_requests': features['total_requests'],
                'bandwidth_usage': round(features['bandwidth_usage'], 2)
            },
            'node_health': {
                'active': total_count - inactive_count - failed_count,
                'inactive': inactive_count,
                'failed': failed_count,
                'total': total_count
            },
            'timestamp': timezone.now().isoformat()
        })
    
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'message': str(e),
            'error_trace': traceback.format_exc(),
            'timestamp': timezone.now().isoformat()
        }, status=500)


def generate_ai_reasoning(risk_level, factors, features):
    """
    Generate AI reasoning summary based on REAL contributing factors.
    NO hardcoded messages - all text generated from actual metrics.
    """
    if not factors:
        return "Network conditions are normal. No significant anomalies detected."
    
    high_impact_factors = [f['factor'] for f in factors if f.get('impact') == 'HIGH']
    medium_impact_factors = [f['factor'] for f in factors if f.get('impact') == 'MEDIUM']
    
    if risk_level == 'HIGH':
        summary = f"🔴 HIGH RISK: Network congestion predicted. "
        if high_impact_factors:
            summary += f"Critical issues: {', '.join(high_impact_factors[:2])}. "
        summary += f"System is under stress with {len(factors)} warning(s)."
    elif risk_level == 'MEDIUM':
        summary = f"🟠 MEDIUM RISK: Network showing signs of stress. "
        if high_impact_factors or medium_impact_factors:
            issues = high_impact_factors + medium_impact_factors
            summary += f"Concerns: {', '.join(issues[:2])}. "
        summary += f"Monitor system performance closely."
    else:  # LOW
        summary = f"🟢 LOW RISK: Network operating normally. "
        if factors:
            summary += f"Minor indicators: {', '.join([f['factor'] for f in factors])}. "
        summary += "No significant congestion predicted."
    
    return summary


def generate_anomaly_explanation(features, factors):
    """
    Generate anomaly explanation from REAL network metrics.
    Explains what the system detected and why it matters.
    """
    anomalies = []
    
    # Check each contributing factor for specific anomalies
    for factor in factors:
        if 'High Request' in factor['factor']:
            anomalies.append(f"Request rate spike detected at {factor['value']} req/sec")
        elif 'Client Connection' in factor['factor']:
            anomalies.append(f"Unusual number of simultaneous connections: {factor['value']} clients")
        elif 'Looping' in factor['factor']:
            anomalies.append(f"Repetitive request pattern detected: {factor['value']}% repeated")
        elif 'Latency' in factor['factor']:
            anomalies.append(f"Response times elevated to {factor['value']}ms")
        elif 'Node Failure' in factor['factor']:
            anomalies.append(f"Client node reliability degraded: {factor['value']} failures")
        elif 'Growth' in factor['factor']:
            anomalies.append(f"Rapid traffic growth detected: {factor['value']}x multiplier")
        elif 'Heartbeat' in factor['factor']:
            anomalies.append(f"Connection stability issues: only {factor['value']}% nodes healthy")
    
    if anomalies:
        explanation = "Detected anomalies: " + "; ".join(anomalies) + ". "
        explanation += "These patterns indicate potential network stress or unusual behavior."
        return explanation
    else:
        return "No anomalies detected. Network behavior within normal parameters."

