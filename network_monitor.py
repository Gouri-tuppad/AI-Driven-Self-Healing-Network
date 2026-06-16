from django.utils import timezone
from django.db.models import Count
from datetime import timedelta
from .models import ActiveConnection, NetworkEvent, ServerNode, TrafficLog


class NetworkMonitor:
    MAX_CAPACITY_PER_SERVER = 4  # Congestion triggers when exceeds 4 (i.e., 5+ devices)
    
    @staticmethod
    def get_active_connections_count():
        """Get total active connections - ONLY REAL CONNECTIONS"""
        return ActiveConnection.objects.filter(is_active=True).count()
    
    @staticmethod
    def check_network_health():
        """
        Monitor network health from REAL connections only.
        Issues are only detected when more than 4 real PCs are connected (5+ devices).
        Returns a list of detected network issues.
        """
        active_count = NetworkMonitor.get_active_connections_count()
        issues = []
        
        # If connections are at or below capacity, mark congestion as resolved
        if active_count <= NetworkMonitor.MAX_CAPACITY_PER_SERVER:
            NetworkEvent.objects.filter(
                event_type='CONGESTION',
                resolved=False
            ).update(resolved=True, resolved_at=timezone.now())
            return issues
        
        # ===== CONGESTION ISSUE: More than 10 real connections =====
        excess = active_count - NetworkMonitor.MAX_CAPACITY_PER_SERVER
        event = NetworkMonitor._create_or_update_congestion_event(active_count)
        issues.append({
            'type': 'CONGESTION',
            'severity': 'CRITICAL',
            'description': f'🔴 Network Congestion: {active_count} PCs connected, exceeding capacity of {NetworkMonitor.MAX_CAPACITY_PER_SERVER}. Excess: {excess} connection(s).',
            'event': event,
            'affected_pcs': active_count,
            'timestamp': event.timestamp if event else timezone.now()
        })
        
        # ===== IP ADDRESS CONFLICT: Multiple PCs using same IP =====
        ip_groups = ActiveConnection.objects.filter(
            is_active=True
        ).values('ip_address').annotate(count=Count('id')).filter(count__gt=1)
        
        for group in ip_groups:
            conflicting_students = list(ActiveConnection.objects.filter(
                is_active=True, 
                ip_address=group['ip_address']
            ).select_related('student__user').values_list('student__user__username', flat=True))
            
            event = NetworkMonitor._create_ip_conflict_event(group['ip_address'], conflicting_students)
            issues.append({
                'type': 'IP_CONFLICT',
                'severity': 'CRITICAL',
                'description': f'⚠️ IP Address Conflict: {group["ip_address"]} is shared by {len(conflicting_students)} PCs: {", ".join(conflicting_students)}',
                'event': event,
                'conflicting_ip': group['ip_address'],
                'affected_students': conflicting_students,
                'affected_pcs': len(conflicting_students),
                'timestamp': event.timestamp if event else timezone.now()
            })
        
        # ===== NODE FAILURE: Server node overloaded or unhealthy =====
        server_nodes = ServerNode.objects.all()
        for node in server_nodes:
            node_connections = ActiveConnection.objects.filter(
                is_active=True, 
                server_node=node
            ).count()
            
            if node_connections > node.max_capacity:
                affected_students = list(ActiveConnection.objects.filter(
                    is_active=True,
                    server_node=node
                ).select_related('student__user').values_list('student__user__username', flat=True))
                
                event = NetworkMonitor._create_node_failure_event(node, node_connections, affected_students)
                issues.append({
                    'type': 'NODE_FAILURE',
                    'severity': 'CRITICAL',
                    'description': f'❌ Node Failure: {node.name} overloaded with {node_connections}/{node.max_capacity} connections. Connected students: {", ".join(affected_students)}',
                    'event': event,
                    'node_name': node.name,
                    'node_ip': node.ip_address,
                    'connections': node_connections,
                    'max_capacity': node.max_capacity,
                    'affected_students': affected_students,
                    'affected_pcs': len(affected_students),
                    'timestamp': event.timestamp if event else timezone.now()
                })
        
        # ===== LOAD BALANCING RECOMMENDATION =====
        if issues:
            issues.append({
                'type': 'LOAD_BALANCING',
                'severity': 'WARNING',
                'description': f'💡 Load Balancing Recommended: {active_count} PCs connected. Distribute connections across {ServerNode.objects.filter(is_healthy=True).count()} server nodes to prevent congestion.',
                'event': None,
                'action': 'balance_load',
                'affected_pcs': active_count,
                'timestamp': timezone.now()
            })
        
        return issues
    
    @staticmethod
    def _create_or_update_congestion_event(active_count):
        """Create or update congestion event from real connection data"""
        # Check if recent congestion event exists (within 60 seconds)
        existing = NetworkEvent.objects.filter(
            event_type='CONGESTION',
            resolved=False
        ).order_by('-timestamp').first()
        
        if existing and (timezone.now() - existing.timestamp) < timedelta(seconds=60):
            return existing
        
        # Create new event
        event = NetworkEvent.objects.create(
            event_type='CONGESTION',
            description=f'Network Congestion: {active_count} real connections exceed capacity of {NetworkMonitor.MAX_CAPACITY_PER_SERVER}',
            severity='CRITICAL',
            resolved=False
        )
        return event
    
    @staticmethod
    def _create_ip_conflict_event(ip_address, usernames):
        """Create IP conflict event from real data"""
        # Check if event for this IP already exists
        existing = NetworkEvent.objects.filter(
            event_type='IP_CONFLICT',
            description__contains=ip_address,
            resolved=False
        ).first()
        
        if existing:
            return existing
        
        event = NetworkEvent.objects.create(
            event_type='IP_CONFLICT',
            description=f'IP Address Conflict Detected: {ip_address} shared by {len(usernames)} students: {", ".join(usernames)}',
            severity='CRITICAL',
            resolved=False
        )
        return event
    
    @staticmethod
    def _create_node_failure_event(node, connection_count, affected_students):
        """Create node failure event from real connection data"""
        # Check if event for this node already exists
        existing = NetworkEvent.objects.filter(
            event_type='NODE_FAILURE',
            affected_node=node,
            resolved=False
        ).first()
        
        if existing:
            return existing
        
        event = NetworkEvent.objects.create(
            event_type='NODE_FAILURE',
            affected_node=node,
            description=f'Node {node.name} ({node.ip_address}) overloaded with {connection_count}/{node.max_capacity} connections from: {", ".join(affected_students)}',
            severity='CRITICAL',
            resolved=False
        )
        return event
    
    @staticmethod
    def get_network_status():
        """
        Get real-time network status based on ACTUAL CONNECTED PCs.
        No fake data - all data comes from real ActiveConnection records.
        """
        active_count = NetworkMonitor.get_active_connections_count()
        
        # Get REAL connected students with their details
        connections = ActiveConnection.objects.filter(
            is_active=True
        ).select_related('student__user', 'server_node')
        
        connected_list = []
        for conn in connections:
            connected_list.append({
                'username': conn.student.user.username,
                'student_id': conn.student.student_id,
                'ip_address': conn.ip_address,
                'server_node': conn.server_node.name if conn.server_node else 'Unassigned',
                'connected_at': conn.connected_at.isoformat(),
                'last_activity': conn.last_activity.isoformat()
            })
        
        # Get real issues only when connections detected
        issues = NetworkMonitor.check_network_health()
        
        # Get server node status
        nodes_status = []
        for node in ServerNode.objects.all():
            node_conns = ActiveConnection.objects.filter(is_active=True, server_node=node).count()
            nodes_status.append({
                'name': node.name,
                'ip_address': node.ip_address,
                'is_healthy': node.is_healthy,
                'connections': node_conns,
                'max_capacity': node.max_capacity,
                'utilization_percent': round((node_conns / node.max_capacity * 100), 1) if node.max_capacity > 0 else 0
            })
        
        return {
            'total_active_connections': active_count,
            'max_capacity': NetworkMonitor.MAX_CAPACITY_PER_SERVER,
            'capacity_exceeded': active_count > NetworkMonitor.MAX_CAPACITY_PER_SERVER,
            'excess_connections': max(0, active_count - NetworkMonitor.MAX_CAPACITY_PER_SERVER),
            'connected_pcs': connected_list,
            'active_issues': issues,
            'issue_count': len([i for i in issues if i['type'] != 'LOAD_BALANCING']),
            'nodes_status': nodes_status,
            'overall_status': 'CRITICAL' if active_count > NetworkMonitor.MAX_CAPACITY_PER_SERVER else 'NORMAL',
            'timestamp': timezone.now().isoformat()
        }
