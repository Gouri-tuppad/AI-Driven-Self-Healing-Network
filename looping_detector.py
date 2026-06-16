"""
Network Looping Detection System
Detects network flooding and looping issues caused by excessive repeated requests
Uses only real request data from RequestLog database
"""

from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from network_sim.models import RequestLog, NetworkEvent
from students.models import Student


class LoopingDetector:
    """Detect network looping and flooding behavior from real request logs"""
    
    # Configurable thresholds
    DEFAULT_REQUEST_THRESHOLD = 20  # requests
    DEFAULT_TIME_WINDOW = 10  # seconds
    DEFAULT_DETECTION_INTERVAL = 300  # seconds (5 minutes)
    
    @staticmethod
    def detect_looping_issues(request_threshold=None, time_window_seconds=None):
        """
        Detect looping/flooding issues from real request logs.
        
        Args:
            request_threshold: Number of requests to trigger alert (default: 20)
            time_window_seconds: Time window in seconds (default: 10)
        
        Returns:
            List of detected looping issues with details
        """
        if request_threshold is None:
            request_threshold = LoopingDetector.DEFAULT_REQUEST_THRESHOLD
        if time_window_seconds is None:
            time_window_seconds = LoopingDetector.DEFAULT_TIME_WINDOW
        
        looping_issues = []
        now = timezone.now()
        
        # Check IP addresses with high request frequency
        # Get request counts per IP in the time window
        cutoff_time = now - timedelta(seconds=time_window_seconds)
        
        # Aggregate requests by IP address and user
        ip_request_stats = RequestLog.objects.filter(
            timestamp__gte=cutoff_time
        ).values('ip_address', 'user').annotate(
            request_count=Count('id')
        ).filter(
            request_count__gte=request_threshold
        ).order_by('-request_count')
        
        for stat in ip_request_stats:
            ip_address = stat['ip_address']
            user_id = stat['user']
            request_count = stat['request_count']
            
            # Get more details about this IP/user combination
            requests = RequestLog.objects.filter(
                ip_address=ip_address,
                user_id=user_id,
                timestamp__gte=cutoff_time
            ).order_by('timestamp')
            
            if requests.exists():
                first_request = requests.first()
                last_request = requests.last()
                time_span = (last_request.timestamp - first_request.timestamp).total_seconds()
                
                # Calculate request frequency (requests per second)
                if time_span > 0:
                    request_frequency = request_count / time_span
                else:
                    request_frequency = float('inf')
                
                # Get user information
                try:
                    from django.contrib.auth.models import User
                    user = User.objects.get(id=user_id) if user_id else None
                    username = user.username if user else "Unknown"
                    
                    # Try to get student
                    student = None
                    if user:
                        student = Student.objects.filter(user=user).first()
                except:
                    username = f"User#{user_id}" if user_id else "Anonymous"
                    student = None
                
                # Get the paths being requested
                paths = list(requests.values_list('path', flat=True).distinct())
                
                # Determine if this is a genuine looping issue
                severity = LoopingDetector._calculate_severity(request_count, request_frequency)
                
                issue = {
                    'ip_address': ip_address,
                    'username': username,
                    'user_id': user_id,
                    'request_count': request_count,
                    'time_window_seconds': time_window_seconds,
                    'request_frequency': round(request_frequency, 2),  # requests per second
                    'time_span_seconds': round(time_span, 2),
                    'severity': severity,
                    'paths': paths[:5],  # Top 5 paths being requested
                    'first_request': first_request.timestamp,
                    'last_request': last_request.timestamp,
                    'methods': list(requests.values_list('method', flat=True).distinct()),
                    'status_codes': list(requests.values_list('status_code', flat=True).distinct()),
                }
                
                looping_issues.append(issue)
        
        return looping_issues
    
    @staticmethod
    def _calculate_severity(request_count, request_frequency):
        """
        Calculate severity level based on request patterns
        
        Severity levels:
        - LOW: 20-50 requests, freq < 5 req/s
        - MEDIUM: 51-100 requests OR freq 5-10 req/s
        - HIGH: 101-200 requests OR freq 10-20 req/s
        - CRITICAL: 200+ requests OR freq 20+ req/s
        """
        if request_count >= 200 or request_frequency >= 20:
            return 'CRITICAL'
        elif request_count >= 101 or request_frequency >= 10:
            return 'HIGH'
        elif request_count >= 51 or request_frequency >= 5:
            return 'MEDIUM'
        else:
            return 'LOW'
    
    @staticmethod
    def get_looping_statistics(time_window_seconds=None):
        """
        Get statistics about looping activity
        
        Returns:
            Dict with aggregated looping statistics
        """
        if time_window_seconds is None:
            time_window_seconds = LoopingDetector.DEFAULT_DETECTION_INTERVAL
        
        now = timezone.now()
        cutoff_time = now - timedelta(seconds=time_window_seconds)
        
        # Total requests in window
        total_requests = RequestLog.objects.filter(
            timestamp__gte=cutoff_time
        ).count()
        
        # Unique IPs with requests
        unique_ips = RequestLog.objects.filter(
            timestamp__gte=cutoff_time
        ).values('ip_address').distinct().count()
        
        # Unique users
        unique_users = RequestLog.objects.filter(
            timestamp__gte=cutoff_time
        ).exclude(user__isnull=True).values('user').distinct().count()
        
        # Average requests per IP
        avg_per_ip = total_requests / unique_ips if unique_ips > 0 else 0
        
        # Detect looping issues
        looping_issues = LoopingDetector.detect_looping_issues(
            request_threshold=20,
            time_window_seconds=10
        )
        
        critical_issues = [i for i in looping_issues if i['severity'] == 'CRITICAL']
        
        return {
            'total_requests': total_requests,
            'unique_ips': unique_ips,
            'unique_users': unique_users,
            'average_requests_per_ip': round(avg_per_ip, 2),
            'looping_issues_detected': len(looping_issues),
            'critical_looping_issues': len(critical_issues),
            'time_window_seconds': time_window_seconds,
            'timestamp': now.isoformat()
        }
    
    @staticmethod
    def get_request_timeline_for_ip(ip_address, limit_seconds=60):
        """
        Get a timeline of requests from a specific IP
        Useful for visualization and detailed analysis
        
        Returns:
            List of requests with timestamps (most recent first)
        """
        now = timezone.now()
        cutoff_time = now - timedelta(seconds=limit_seconds)
        
        requests = RequestLog.objects.filter(
            ip_address=ip_address,
            timestamp__gte=cutoff_time
        ).order_by('-timestamp').values(
            'timestamp', 'path', 'method', 'status_code', 
            'user__username', 'is_authenticated'
        )[:50]
        
        return list(requests)
    
    @staticmethod
    def create_looping_event(issue_data):
        """
        Create a NetworkEvent record for detected looping issue
        
        Args:
            issue_data: Dict from detect_looping_issues()
        
        Returns:
            NetworkEvent instance
        """
        from students.models import Student
        
        description = (
            f"LOOPING ISSUE DETECTED: IP {issue_data['ip_address']} "
            f"({issue_data['username']}) sent {issue_data['request_count']} "
            f"requests in {issue_data['time_window_seconds']}s "
            f"(frequency: {issue_data['request_frequency']} req/s). "
            f"Paths: {', '.join(issue_data['paths'][:3])}"
        )
        
        # Get affected student if available
        affected_student = None
        if issue_data['user_id']:
            try:
                student = Student.objects.filter(
                    user_id=issue_data['user_id']
                ).first()
                affected_student = student
            except:
                pass
        
        event = NetworkEvent.objects.create(
            event_type='LOOPING',
            affected_student=affected_student,
            description=description,
            severity=issue_data['severity'],
            resolved=False
        )
        
        return event
    
    @staticmethod
    def export_looping_report(format='dict'):
        """
        Export comprehensive looping detection report
        
        Args:
            format: 'dict' or 'json'
        
        Returns:
            Detailed report of all looping activity
        """
        import json
        
        issues = LoopingDetector.detect_looping_issues()
        stats = LoopingDetector.get_looping_statistics()
        
        report = {
            'timestamp': timezone.now().isoformat(),
            'statistics': stats,
            'detected_issues': issues,
            'summary': {
                'total_issues': len(issues),
                'critical': len([i for i in issues if i['severity'] == 'CRITICAL']),
                'high': len([i for i in issues if i['severity'] == 'HIGH']),
                'medium': len([i for i in issues if i['severity'] == 'MEDIUM']),
                'low': len([i for i in issues if i['severity'] == 'LOW']),
            }
        }
        
        if format == 'json':
            return json.dumps(report, indent=2, default=str)
        return report
