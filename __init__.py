import json
import socket
from datetime import timedelta
from functools import wraps
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from students.models import Student, Exam, ExamAttempt
from network_sim.models import ServerNode, ActiveConnection, NetworkEvent, TrafficLog, RequestLog
from network_sim.simulator import NetworkSimulator
from network_sim.client_node_monitor import ClientNodeMonitor


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('admin_panel:admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_panel:admin_dashboard')
    if request.method == 'POST':
        username = request.POST.get('username','')
        password = request.POST.get('password','')
        
        # If using hardcoded admin credentials, ensure admin user exists with correct password
        if username == 'admin' and password == 'adminpass':
            admin_user, created = User.objects.get_or_create(username='admin', defaults={
                'email': 'admin@example.com',
                'is_staff': True,
                'is_superuser': True,
            })
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.set_password('adminpass')
            admin_user.save()
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            return redirect('admin_panel:admin_dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    return render(request, 'admin_panel/login.html')


def admin_logout(request):
    logout(request)
    return redirect('admin_panel:admin_login')

@admin_required
def admin_dashboard(request):
    active_connections = ActiveConnection.objects.filter(is_active=True).exclude(student__user__is_staff=True).exclude(student__user__is_superuser=True).select_related('student__user','server_node')
    network_status = NetworkSimulator.get_status()
    now = timezone.now()
    window_start = now - timedelta(minutes=10)

    connection_entries = []

    for conn in active_connections:
        connection_entries.append({
            'username': conn.student.user.username,
            'ip_address': conn.ip_address,
            'timestamp': conn.connected_at,
            'source': 'Active Connection',
        })

    connection_logs = RequestLog.objects.filter(
        timestamp__gte=window_start,
        ip_address__isnull=False
    ).exclude(ip_address='').select_related('user').order_by('-timestamp')[:100]
    for log in connection_logs:
        if log.user and not (log.user.is_staff or log.user.is_superuser):
            connection_entries.append({
                'username': log.user.username,
                'ip_address': log.ip_address,
                'timestamp': log.timestamp,
                'source': 'Connection Log',
            })

    exam_attempts = ExamAttempt.objects.filter(started_at__gte=window_start).select_related('student__user').order_by('-started_at')[:100]
    for attempt in exam_attempts:
        student = attempt.student
        if student.ip_address:
            connection_entries.append({
                'username': student.user.username,
                'ip_address': student.ip_address,
                'timestamp': attempt.started_at,
                'source': 'ExamAttempt',
            })

    logged_in_students = Student.objects.filter(is_online=True, ip_address__isnull=False).select_related('user')
    for student in logged_in_students:
        if student.user and not (student.user.is_staff or student.user.is_superuser):
            connection_entries.append({
                'username': student.user.username,
                'ip_address': student.ip_address,
                'timestamp': student.login_time or now,
                'source': 'Logged-in User',
            })

    ip_users = {}
    for entry in connection_entries:
        ip = entry['ip_address']
        if not ip:
            continue
        ip_users.setdefault(ip, set()).add(entry['username'])

    conflict_ips = {ip for ip, users in ip_users.items() if len(users) > 1}
    ip_conflict_rows = []
    for entry in sorted(connection_entries, key=lambda x: (x['ip_address'], x['timestamp']), reverse=True):
        if entry['ip_address'] in conflict_ips:
            entry['conflict_status'] = 'Potential IP Conflict Detected'
            ip_conflict_rows.append(entry)

    # Get all registered students
    all_students = Student.objects.filter(user__is_staff=False, user__is_superuser=False).select_related('user').values_list('user__username', flat=True).order_by('user__username')
    import json
    students_json = json.dumps(list(all_students))
    
    # Get AI Congestion Prediction
    try:
        from network_sim.ai_congestion_predictor import AICongestionPredictor
        ai_prediction = AICongestionPredictor.get_prediction_summary()
    except Exception as e:
        ai_prediction = {
            'status': 'error',
            'prediction': 'ERROR',
            'error_message': str(e)
        }

    context = {
        'active_clients_count': active_connections.count(),
        'total_students': Student.objects.filter(user__is_staff=False, user__is_superuser=False).count(),
        'total_exams': Exam.objects.count(),
        'total_events': NetworkEvent.objects.count(),
        'recent_events': NetworkEvent.objects.all()[:20],
        'network_status': network_status,
        'congestion_level': network_status['congestion_level'],
        'active_connections': active_connections,
        'students_json': students_json,
        'ip_conflict_rows': ip_conflict_rows,
        'potential_ip_conflict': bool(ip_conflict_rows),
        'conflict_ip_count': len(conflict_ips),
        'conflict_entry_count': len(ip_conflict_rows),
        'ai_prediction': ai_prediction,
    }
    return render(request, 'admin_panel/dashboard.html', context)

@admin_required
def admin_clients(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'clear_clients':
            # Disconnect all active non-admin client connections and flag students as disconnected by admin.
            disconnect_qs = ActiveConnection.objects.filter(is_active=True).exclude(student__user__is_staff=True).exclude(student__user__is_superuser=True)
            disconnect_count = disconnect_qs.count()
            disconnect_qs.update(is_active=False, last_activity=timezone.now())
            Student.objects.filter(user__is_staff=False, user__is_superuser=False, is_online=True).update(is_online=False, disconnected_by_admin=True)
            NetworkEvent.objects.create(
                event_type='DISCONNECTION',
                description=f'Admin disconnected all active clients ({disconnect_count}).',
                severity='HIGH',
                resolved=False
            )
            messages.success(request, f'All {disconnect_count} active clients have been disconnected.')
            return redirect('admin_panel:admin_clients')
        
        elif request.POST.get('action') == 'remove_client':
            # Disconnect a specific client
            student_id = request.POST.get('student_id')
            try:
                student = Student.objects.get(id=student_id)
                
                # Disconnect all active connections for this student
                client_connections = ActiveConnection.objects.filter(
                    student=student,
                    is_active=True
                )
                disconnect_count = client_connections.count()
                
                # Update all connections to inactive
                client_connections.update(is_active=False, last_activity=timezone.now())
                
                # Update student status
                student.is_online = False
                student.disconnected_by_admin = True
                student.save()
                
                # Create network event
                NetworkEvent.objects.create(
                    event_type='DISCONNECTION',
                    description=f'Admin disconnected client: {student.user.username} ({disconnect_count} connection(s)).',
                    severity='HIGH',
                    affected_student=student,
                    resolved=False
                )
                
                messages.success(request, f'Client {student.user.username} and all their {disconnect_count} connection(s) have been disconnected.')
                return redirect('admin_panel:admin_clients')
            except Student.DoesNotExist:
                messages.error(request, 'Student not found.')
                return redirect('admin_panel:admin_clients')

    students = Student.objects.filter(user__is_staff=False, user__is_superuser=False).select_related('user')
    active_connections = ActiveConnection.objects.filter(is_active=True).exclude(student__user__is_staff=True).exclude(student__user__is_superuser=True).select_related('student','server_node')
    
    # Convert connected_at to IST (UTC+5:30)
    from datetime import timedelta
    ist_offset = timedelta(hours=5, minutes=30)
    for conn in active_connections:
        # Convert UTC datetime to IST
        conn.connected_at_ist = (conn.connected_at + ist_offset).strftime('%Y-%m-%d %H:%M:%S')
    
    return render(request, 'admin_panel/clients.html', {'students':students,'active_connections':active_connections})

@admin_required
def admin_network_monitoring(request):
    """Display real-time network monitoring dashboard"""
    from network_sim.network_monitor import NetworkMonitor
    
    network_status = NetworkMonitor.get_network_status()
    
    context = {
        'total_connections': network_status['total_active_connections'],
        'max_capacity': network_status['max_capacity'],
        'capacity_exceeded': network_status['capacity_exceeded'],
        'excess_connections': network_status['excess_connections'],
        'connected_pcs': network_status['connected_pcs'],
        'active_issues': network_status['active_issues'],
        'nodes_status': network_status['nodes_status'],
        'network_status': network_status['overall_status']
    }
    return render(request, 'admin_panel/network_monitoring_section.html', context)

@admin_required
def admin_network_logs(request):
    filter_type = request.GET.get('type','')
    events = NetworkEvent.objects.all().select_related('affected_student','affected_node')
    if filter_type:
        events = events.filter(event_type=filter_type)
    event_types = NetworkEvent.EVENT_TYPES
    return render(request, 'admin_panel/network_logs.html', {'events':events,'event_types':event_types,'filter_type':filter_type})

@admin_required
def admin_traffic(request):
    return render(request, 'admin_panel/traffic.html')

@admin_required
def api_dashboard_data(request):
    server_nodes = []
    for node in ServerNode.objects.all():
        server_nodes.append({'name':node.name,'ip_address':node.ip_address,'is_healthy':node.is_healthy,'current_load':node.current_load,'max_capacity':node.max_capacity})
    recent_events = []
    for event in NetworkEvent.objects.all()[:20]:
        recent_events.append({'event_type':event.event_type,'description':event.description,'severity':event.severity,'timestamp':event.timestamp.isoformat(),'resolved':event.resolved})
    network_status = NetworkSimulator.get_status()
    return JsonResponse({'active_clients_count': ActiveConnection.objects.filter(is_active=True).count(),'server_nodes':server_nodes,'recent_events':recent_events,'congestion_level':network_status['congestion_level']})

@admin_required
def api_traffic_data(request):
    logs = TrafficLog.objects.all().order_by('-timestamp')[:50]
    logs_list = list(logs)
    logs_list.reverse()
    timestamps = [log.timestamp.strftime('%H:%M:%S') for log in logs_list]
    connections = [log.active_connections for log in logs_list]
    bandwidth = [log.bandwidth_usage for log in logs_list]
    latency = [log.latency_ms for log in logs_list]
    packets = [log.packet_count for log in logs_list]
    return JsonResponse({'timestamps':timestamps,'connections':connections,'bandwidth':bandwidth,'latency':latency,'packets':packets})

@admin_required
def api_resolve_event(request, event_id):
    if request.method != 'POST':
        return JsonResponse({'success':False,'message':'POST required.'}, status=405)
    if not request.user.is_authenticated or not request.user.is_staff:
        return JsonResponse({'success':False,'message':'Unauthorized.'}, status=403)
    event = get_object_or_404(NetworkEvent, id=event_id)
    event.resolved = True
    event.resolved_at = timezone.now()
    event.save(update_fields=['resolved','resolved_at'])
    return JsonResponse({'success':True,'message':'Event resolved.'})

@admin_required
def client_node_failure_monitoring(request):
    """
    Monitor client node status and detect failures.
    Displays:
    - Client nodes with ACTIVE/INACTIVE/NODE_FAILURE status
    - Last activity and connection duration
    - Central server health status
    """
    timeout_seconds = int(request.GET.get('timeout', 60))
    
    # Get network summary
    network_summary = ClientNodeMonitor.get_network_summary(timeout_seconds)
    
    # Convert connected_at times to IST (UTC+5:30)
    ist_offset = timedelta(hours=5, minutes=30)
    for node in network_summary['client_nodes']:
        if node['node_status'].connected_at:
            node['connected_at_ist'] = (node['node_status'].connected_at + ist_offset).strftime('%Y-%m-%d %H:%M:%S')
        else:
            node['connected_at_ist'] = 'Unknown'
    
    context = {
        'total_nodes': network_summary['total_nodes'],
        'active_nodes': network_summary['active_nodes'],
        'inactive_nodes': network_summary['inactive_nodes'],
        'failed_nodes': network_summary['failed_nodes'],
        'server_status': network_summary['server_status'],
        'server_response_time': network_summary['server_response_time'],
        'client_nodes': network_summary['client_nodes'],
        'timeout_seconds': timeout_seconds,
        'page_title': 'Client Node Failure Monitoring',
    }
    
    return render(request, 'admin_panel/client_node_monitoring.html', context)

@admin_required
def api_client_node_status(request):
    """
    API endpoint for real-time client node status.
    Returns JSON data for AJAX updates.
    """
    timeout_seconds = int(request.GET.get('timeout', 60))
    network_summary = ClientNodeMonitor.get_network_summary(timeout_seconds)
    
    client_nodes_data = []
    for node in network_summary['client_nodes']:
        client_nodes_data.append({
            'username': node['username'],
            'ip_address': str(node['ip_address']) if node['ip_address'] else 'Unknown',
            'status': node['status'],
            'status_icon': node['status_badge']['icon'],
            'last_activity': node['last_activity_formatted'],
            'connection_duration': node['connection_duration'],
        })
    
    return JsonResponse({
        'total_nodes': network_summary['total_nodes'],
        'active_nodes': network_summary['active_nodes'],
        'inactive_nodes': network_summary['inactive_nodes'],
        'failed_nodes': network_summary['failed_nodes'],
        'server_status': network_summary['server_status'],
        'server_response_time': network_summary['server_response_time'],
        'client_nodes': client_nodes_data,
        'timestamp': timezone.now().isoformat(),
    })


# ============================================================================
# REAL-TIME NETWORK TOPOLOGY VISUALIZATION VIEW
# ============================================================================
# This view provides the dashboard for displaying live network topology
# Uses real data from ClientNodeStatus model - NO fake/hardcoded nodes

@admin_required
def network_topology_visualization(request):
    """
    Display LIVE NETWORK TOPOLOGY dashboard.
    
    Shows real-time visualization of:
    - Central Django server (central node)
    - Connected client nodes with actual status from ClientNodeStatus
    - Network connections and communication paths
    - Node status indicators: Green (ACTIVE), Orange (INACTIVE), Red (NODE_FAILURE), Blue (RECOVERED)
    - Real-time updates via AJAX polling
    
    Uses ONLY real backend data:
    - ClientNodeStatus: actual client node status tracking
    - Heartbeat records: communication health
    - Connection logs: active connections
    
    Data is fetched dynamically from API endpoints, not hardcoded.
    """
    from network_sim.models import ClientNodeStatus
    
    # Get initial network stats
    client_statuses = ClientNodeStatus.objects.all()
    total_nodes = client_statuses.count()
    active_nodes = client_statuses.filter(status='ACTIVE').count()
    inactive_nodes = client_statuses.filter(status='INACTIVE').count()
    failed_nodes = client_statuses.filter(status='NODE_FAILURE').count()
    
    # Calculate health score
    if total_nodes > 0:
        health_score = round((active_nodes / total_nodes) * 100, 1)
    else:
        health_score = 0
    
    context = {
        'page_title': 'Live Network Topology',
        'total_nodes': total_nodes,
        'active_nodes': active_nodes,
        'inactive_nodes': inactive_nodes,
        'failed_nodes': failed_nodes,
        'health_score': health_score,
        'network_status': 'HEALTHY' if health_score >= 80 else 'DEGRADED' if health_score >= 50 else 'CRITICAL',
        'refresh_interval_ms': 3000,  # Refresh every 3 seconds
    }
    
    return render(request, 'admin_panel/network_topology.html', context)


# ============================================================================
# EXPLAINABLE AI ANALYSIS PANEL VIEW
# ============================================================================
# Displays AI predictions WITH EXPLANATIONS based on REAL network metrics
# Explains WHY congestion/anomalies are predicted

@admin_required
def ai_analysis_panel(request):
    """
    Display EXPLAINABLE AI ANALYSIS dashboard.
    
    Shows AI-driven monitoring with:
    - Current risk level prediction (LOW/MEDIUM/HIGH)
    - Confidence percentage based on ML model
    - Contributing factors from REAL network metrics
    - AI reasoning explaining why this prediction
    - Anomaly detection from actual network behavior
    - Color-coded risk indicators (Green/Orange/Red)
    - Auto-updating via AJAX every 3 seconds
    
    Uses ONLY real data from backend:
    - requests_per_second: Current request rate
    - active_client_count: Connected clients
    - looping_frequency: Repeated requests pattern
    - average_latency: Network response time
    - failed_nodes: Failed client nodes
    - heartbeat_stability: Connection health
    - traffic_growth: Connection growth rate
    
    NO hardcoded predictions or fake AI reasoning.
    All explanations generated from actual network metrics.
    """
    try:
        from network_sim.ai_congestion_predictor import AICongestionPredictor
        from network_sim.models import ClientNodeStatus
        
        # Get current AI prediction
        features = AICongestionPredictor.extract_features(time_window_seconds=300)
        prediction_data = AICongestionPredictor.predict_congestion()
        
        # Extract key metrics for initial display
        current_metrics = {
            'requests_per_second': round(features['requests_per_second'], 3),
            'active_clients': features['active_client_count'],
            'looping_frequency': round(features['looping_frequency'], 4),
            'average_latency_ms': round(features['average_latency'], 1),
            'failed_nodes': features['failed_nodes'],
        }
        
        # Get node health status
        client_statuses = ClientNodeStatus.objects.all()
        node_health = {
            'active': client_statuses.filter(status='ACTIVE').count(),
            'inactive': client_statuses.filter(status='INACTIVE').count(),
            'failed': client_statuses.filter(status='NODE_FAILURE').count(),
            'total': client_statuses.count(),
        }
        
        context = {
            'page_title': 'AI Analysis Panel',
            'current_metrics': current_metrics,
            'node_health': node_health,
            'refresh_interval_ms': 3000,  # Refresh every 3 seconds
        }
        
        return render(request, 'admin_panel/ai_analysis_panel.html', context)
    
    except Exception as e:
        import traceback
        print(f"Error in ai_analysis_panel: {e}")
        print(traceback.format_exc())
        
        context = {
            'page_title': 'AI Analysis Panel',
            'error': str(e),
        }
        return render(request, 'admin_panel/ai_analysis_panel.html', context)


# ============================================================================
# SELF-HEALING TIMELINE & RECOVERY VISUALIZATION
# ============================================================================
# Track and display real recovery events from backend node monitoring
# Shows status transitions and recovery activities

@admin_required
def self_healing_timeline(request):
    """
    Display SELF-HEALING EVENT TIMELINE dashboard.
    
    Shows real recovery events from backend monitoring:
    - Node failure detected (from ClientNodeStatus failure_detected_at)
    - Heartbeat timeout (from last_heartbeat comparison)
    - Recovery attempts (from status changes)
    - Heartbeat restored (from last_heartbeat updates)
    - Node recovered (from status back to ACTIVE)
    
    Timeline displays ONLY real events from:
    - ClientNodeStatus model: node status tracking
    - NetworkEvent model: recovery/failure events
    - Heartbeat records: communication health
    
    Color coding:
    - Red: Node failure detected
    - Orange: Recovery in progress
    - Blue: Recovered
    - Green: Active/Healthy
    
    Uses AJAX for real-time updates every 3 seconds.
    NO fake events or manual insertion - 100% backend driven.
    """
    try:
        from network_sim.models import ClientNodeStatus, NetworkEvent
        
        # Get recovery events (real backend events only)
        recovery_events = get_recovery_timeline_events()
        
        # Get summary statistics
        total_events = len(recovery_events)
        failure_events = len([e for e in recovery_events if e['type'] == 'FAILURE'])
        recovery_events_count = len([e for e in recovery_events if e['type'] == 'RECOVERY'])
        active_nodes = ClientNodeStatus.objects.filter(status='ACTIVE').count()
        failed_nodes = ClientNodeStatus.objects.filter(status='NODE_FAILURE').count()
        
        context = {
            'page_title': 'Self-Healing Timeline',
            'recovery_events': recovery_events[:100],  # Last 100 events
            'total_events': total_events,
            'failure_events': failure_events,
            'recovery_events_count': recovery_events_count,
            'active_nodes': active_nodes,
            'failed_nodes': failed_nodes,
            'refresh_interval_ms': 3000,  # Refresh every 3 seconds
        }
        
        return render(request, 'admin_panel/self_healing_timeline.html', context)
    
    except Exception as e:
        import traceback
        print(f"Error in self_healing_timeline: {e}")
        print(traceback.format_exc())
        
        context = {
            'page_title': 'Self-Healing Timeline',
            'error': str(e),
        }
        return render(request, 'admin_panel/self_healing_timeline.html', context)


def get_recovery_timeline_events():
    """
    Extract real recovery timeline events from backend data.
    
    Sources:
    - ClientNodeStatus: Node failures and status changes
    - NetworkEvent: Recovery events from network monitoring
    
    Returns list of events with:
    - timestamp: When event occurred
    - type: FAILURE/RECOVERY/HEARTBEAT_TIMEOUT/HEARTBEAT_RESTORED
    - username: Student/client name
    - ip_address: Node IP address
    - status: Current node status
    - description: Event description
    - color_class: Bootstrap color class (danger/warning/info/success)
    """
    from network_sim.models import ClientNodeStatus, NetworkEvent
    from datetime import timedelta
    
    events = []
    
    # Get all network events related to failures and recovery (REAL backend events)
    network_recovery_events = NetworkEvent.objects.filter(
        event_type__in=['NODE_FAILURE', 'RECOVERY']
    ).select_related('affected_student', 'affected_node').order_by('-timestamp')
    
    for event in network_recovery_events:
        event_type = 'FAILURE' if event.event_type == 'NODE_FAILURE' else 'RECOVERY'
        events.append({
            'timestamp': event.timestamp,
            'type': event_type,
            'username': event.affected_student.user.username if event.affected_student else 'Unknown',
            'ip_address': event.affected_student.ip_address if event.affected_student else 'N/A',
            'status': 'Node Failure' if event_type == 'FAILURE' else 'Recovered',
            'description': event.description,
            'severity': event.severity,
            'color_class': 'danger' if event_type == 'FAILURE' else 'success',
            'icon': '🔴' if event_type == 'FAILURE' else '✅',
        })
    
    # Get client node status changes (heartbeat/activity tracking)
    client_nodes = ClientNodeStatus.objects.all().select_related('student')
    for node in client_nodes:
        # Check for heartbeat timeout (no heartbeat in heartbeat_timeout_seconds)
        if node.last_heartbeat:
            time_since_heartbeat = timezone.now() - node.last_heartbeat
            if time_since_heartbeat > timedelta(seconds=node.heartbeat_timeout_seconds):
                # Heartbeat timeout detected - add event if node failed
                if node.status == 'NODE_FAILURE' and node.failure_detected_at:
                    events.append({
                        'timestamp': node.failure_detected_at,
                        'type': 'HEARTBEAT_TIMEOUT',
                        'username': node.student.user.username,
                        'ip_address': str(node.ip_address) if node.ip_address else 'N/A',
                        'status': 'Heartbeat Timeout',
                        'description': f'Heartbeat timeout for {node.student.user.username}',
                        'severity': 'HIGH',
                        'color_class': 'warning',
                        'icon': '⏱️',
                    })
        
        # Check for heartbeat restored (active node with recent heartbeat)
        if node.status == 'ACTIVE' and node.last_heartbeat:
            time_since_heartbeat = timezone.now() - node.last_heartbeat
            if time_since_heartbeat < timedelta(seconds=node.heartbeat_timeout_seconds):
                events.append({
                    'timestamp': node.last_heartbeat,
                    'type': 'HEARTBEAT_RESTORED',
                    'username': node.student.user.username,
                    'ip_address': str(node.ip_address) if node.ip_address else 'N/A',
                    'status': 'Heartbeat Restored',
                    'description': f'Heartbeat restored for {node.student.user.username}',
                    'severity': 'LOW',
                    'color_class': 'info',
                    'icon': '💚',
                })
        
        # Active node event
        if node.status == 'ACTIVE':
            events.append({
                'timestamp': node.last_activity or node.record_created_at,
                'type': 'ACTIVE',
                'username': node.student.user.username,
                'ip_address': str(node.ip_address) if node.ip_address else 'N/A',
                'status': 'Active',
                'description': f'{node.student.user.username} is active',
                'severity': 'LOW',
                'color_class': 'success',
                'icon': '🟢',
            })
    
    # Sort by timestamp (newest first)
    events = sorted(events, key=lambda x: x['timestamp'], reverse=True)
    
    return events


@admin_required
def api_self_healing_events(request):
    """
    API endpoint for real-time self-healing timeline events.
    
    Returns JSON with:
    - recovery_events: List of timeline events (max 100)
    - summary: Statistics about events
    - timestamp: When data was generated
    
    All data is REAL from backend - NO fake events.
    """
    try:
        recovery_events = get_recovery_timeline_events()[:100]
        
        # Calculate statistics
        failure_count = len([e for e in recovery_events if e['type'] == 'FAILURE'])
        recovery_count = len([e for e in recovery_events if e['type'] == 'RECOVERY'])
        active_count = len([e for e in recovery_events if e['type'] == 'ACTIVE'])
        
        # Format events for JSON
        events_data = []
        for event in recovery_events:
            events_data.append({
                'timestamp': event['timestamp'].isoformat(),
                'type': event['type'],
                'username': event['username'],
                'ip_address': event['ip_address'],
                'status': event['status'],
                'description': event['description'],
                'severity': event['severity'],
                'color_class': event['color_class'],
                'icon': event['icon'],
            })
        
        return JsonResponse({
            'success': True,
            'recovery_events': events_data,
            'summary': {
                'total_events': len(recovery_events),
                'failure_events': failure_count,
                'recovery_events': recovery_count,
                'active_nodes': active_count,
            },
            'timestamp': timezone.now().isoformat(),
        })
    
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'message': str(e),
            'error_trace': traceback.format_exc(),
            'timestamp': timezone.now().isoformat(),
        }, status=500)
