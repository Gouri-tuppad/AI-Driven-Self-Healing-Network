"""
AI-Based Congestion Prediction System
Uses real network data to predict congestion BEFORE it happens.
"""

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Avg
import pickle
import os

# Lazy imports for optional dependencies
pd = None
np = None
StandardScaler = None
RandomForestClassifier = None
DecisionTreeClassifier = None
LogisticRegression = None

def _ensure_dependencies():
    """Lazily import required dependencies"""
    global pd, np, StandardScaler, RandomForestClassifier, DecisionTreeClassifier, LogisticRegression
    
    if pd is None:
        try:
            import pandas as pd_import
            import numpy as np_import
            from sklearn.preprocessing import StandardScaler as SS
            from sklearn.ensemble import RandomForestClassifier as RFC
            from sklearn.tree import DecisionTreeClassifier as DTC
            from sklearn.linear_model import LogisticRegression as LR
            
            pd = pd_import
            np = np_import
            StandardScaler = SS
            RandomForestClassifier = RFC
            DecisionTreeClassifier = DTC
            LogisticRegression = LR
        except ImportError as e:
            raise ImportError(f"Required dependencies missing: {e}")

from .models import RequestLog, TrafficLog, ActiveConnection, ClientNodeStatus, NetworkEvent


class AICongestionPredictor:
    """AI-powered congestion prediction using machine learning"""
    
    # Risk levels
    RISK_LOW = "LOW"
    RISK_MEDIUM = "MEDIUM"
    RISK_HIGH = "HIGH"
    
    # Model configuration
    MODEL_TYPE = "RandomForest"  # Options: RandomForest, DecisionTree, LogisticRegression
    MIN_SAMPLES_FOR_TRAINING = 5  # Minimum data points to train
    PREDICTION_WINDOW = 300  # 5 minutes look-ahead window
    TRAINING_WINDOW = 3600  # 1 hour of historical data for training
    
    # Thresholds for risk classification
    CONGESTION_THRESHOLD = 3  # Active connections threshold (triggers at 5+ devices)
    LOOPING_THRESHOLD = 15  # Requests per 10s (more sensitive)
    TRAFFIC_GROWTH_THRESHOLD = 1.3  # 30% growth rate (more sensitive)
    
    @staticmethod
    def extract_features(time_window_seconds=None):
        """
        Extract features from real network data.
        
        Features:
        - requests_per_second: Current request rate
        - active_client_count: Number of active connections
        - repeated_request_count: Requests to same endpoint
        - total_requests: Total requests in window
        - looping_frequency: Frequency of repeated requests
        - average_latency: Network latency
        - bandwidth_usage: Current bandwidth
        - connection_growth: Growth rate of connections
        - high_severity_events: Count of recent high-severity events
        """
        if time_window_seconds is None:
            time_window_seconds = AICongestionPredictor.TRAINING_WINDOW
        
        now = timezone.now()
        window_start = now - timedelta(seconds=time_window_seconds)
        
        # 1. Request frequency
        requests = RequestLog.objects.filter(timestamp__gte=window_start)
        request_count = requests.count()
        requests_per_second = request_count / max(time_window_seconds, 1)
        
        # 2. Active clients
        active_client_count = ActiveConnection.objects.filter(is_active=True).count()
        
        # 3. Repeated requests (looping behavior)
        repeated_requests = requests.values('path', 'ip_address').annotate(
            count=Count('id')
        ).filter(count__gt=5)  # More than 5 requests to same path from same IP
        repeated_request_count = sum([r['count'] for r in repeated_requests])
        looping_frequency = repeated_request_count / max(request_count, 1)
        
        # 4. Traffic logs
        traffic_logs = TrafficLog.objects.filter(timestamp__gte=window_start).order_by('timestamp')
        avg_latency = 0
        bandwidth_usage = 0
        if traffic_logs.exists():
            avg_latency = traffic_logs.aggregate(avg=Avg('latency_ms'))['avg'] or 0
            bandwidth_usage = traffic_logs.aggregate(avg=Avg('bandwidth_usage'))['avg'] or 0
        
        # 5. Connection growth rate
        connections_over_time = traffic_logs.values('timestamp', 'active_connections').order_by('timestamp')
        connection_growth = 1.0
        if len(list(connections_over_time)) > 1:
            data_list = list(connections_over_time)
            first_count = data_list[0]['active_connections']
            last_count = data_list[-1]['active_connections']
            if first_count > 0:
                connection_growth = last_count / first_count
        
        # 6. High severity events
        high_severity_events = NetworkEvent.objects.filter(
            timestamp__gte=window_start,
            severity__in=['HIGH', 'CRITICAL'],
            resolved=False
        ).count()
        
        # 7. Node failures
        failed_nodes = ClientNodeStatus.objects.filter(status='NODE_FAILURE').count()
        
        features = {
            'requests_per_second': requests_per_second,
            'active_client_count': active_client_count,
            'repeated_request_count': repeated_request_count,
            'total_requests': request_count,
            'looping_frequency': looping_frequency,
            'average_latency': avg_latency,
            'bandwidth_usage': bandwidth_usage,
            'connection_growth': connection_growth,
            'high_severity_events': high_severity_events,
            'failed_nodes': failed_nodes,
            'timestamp': now
        }
        
        return features
    
    @staticmethod
    def generate_labels_for_training():
        """
        Generate training labels based on network conditions.
        Uses real network events and thresholds to determine risk level.
        """
        now = timezone.now()
        training_window_start = now - timedelta(seconds=AICongestionPredictor.TRAINING_WINDOW)
        
        training_data = []
        
        # Collect hourly snapshots for training
        for hours_back in range(1, 4):  # Last 3 hours
            snapshot_time = now - timedelta(hours=hours_back)
            window_start = snapshot_time - timedelta(seconds=600)
            window_end = snapshot_time
            
            # Get data for this time window
            requests = RequestLog.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end
            )
            
            traffic = TrafficLog.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end
            )
            
            congestion_events = NetworkEvent.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end,
                event_type='CONGESTION'
            ).exists()
            
            looping_events = NetworkEvent.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end,
                event_type='LOOPING'
            ).exists()
            
            # Determine label
            if requests.count() > 0:
                request_rate = requests.count() / 600  # per 10 seconds
                avg_connections = traffic.aggregate(avg=Avg('active_connections'))['avg'] or 0
                
                if congestion_events or avg_connections > AICongestionPredictor.CONGESTION_THRESHOLD:
                    label = AICongestionPredictor.RISK_HIGH
                elif looping_events or request_rate > AICongestionPredictor.LOOPING_THRESHOLD:
                    label = AICongestionPredictor.RISK_MEDIUM
                else:
                    label = AICongestionPredictor.RISK_LOW
                
                training_data.append({
                    'timestamp': snapshot_time,
                    'label': label,
                    'request_count': requests.count(),
                    'avg_connections': avg_connections
                })
        
        return training_data
    
    @staticmethod
    def build_training_dataset():
        """
        Build complete training dataset from historical data.
        Returns feature matrix and labels.
        """
        _ensure_dependencies()
        
        features_list = []
        labels_list = []
        
        # Generate training data points from historical data
        training_data = AICongestionPredictor.generate_labels_for_training()
        
        if len(training_data) < AICongestionPredictor.MIN_SAMPLES_FOR_TRAINING:
            # Not enough data for training
            return None, None
        
        for data_point in training_data:
            # For each time point, collect features around that time
            window_start = data_point['timestamp'] - timedelta(seconds=300)
            window_end = data_point['timestamp']
            
            requests = RequestLog.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end
            ).count()
            
            active_clients = ActiveConnection.objects.filter(is_active=True).count()
            
            repeated_requests = RequestLog.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end
            ).values('path', 'ip_address').annotate(count=Count('id')).filter(count__gt=5)
            repeated_count = sum([r['count'] for r in repeated_requests])
            
            traffic = TrafficLog.objects.filter(
                timestamp__gte=window_start,
                timestamp__lte=window_end
            )
            
            avg_latency = traffic.aggregate(avg=Avg('latency_ms'))['avg'] or 0
            bandwidth = traffic.aggregate(avg=Avg('bandwidth_usage'))['avg'] or 0
            
            features = {
                'requests_per_second': requests / 300,
                'active_client_count': active_clients,
                'repeated_request_count': repeated_count,
                'total_requests': requests,
                'looping_frequency': repeated_count / max(requests, 1),
                'average_latency': avg_latency,
                'bandwidth_usage': bandwidth,
                'high_severity_events': NetworkEvent.objects.filter(
                    timestamp__gte=window_start,
                    timestamp__lte=window_end,
                    severity__in=['HIGH', 'CRITICAL']
                ).count()
            }
            
            features_list.append(features)
            labels_list.append(data_point['label'])
        
        if len(features_list) < AICongestionPredictor.MIN_SAMPLES_FOR_TRAINING:
            return None, None
        
        df = pd.DataFrame(features_list)
        return df, np.array(labels_list)
    
    @staticmethod
    def train_model():
        """
        Train the congestion prediction model using real network data.
        """
        _ensure_dependencies()
        
        X, y = AICongestionPredictor.build_training_dataset()
        
        if X is None or len(X) < AICongestionPredictor.MIN_SAMPLES_FOR_TRAINING:
            return None
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Select and train model
        if AICongestionPredictor.MODEL_TYPE == "RandomForest":
            model = RandomForestClassifier(
                n_estimators=50,
                max_depth=10,
                random_state=42,
                min_samples_split=5
            )
        elif AICongestionPredictor.MODEL_TYPE == "DecisionTree":
            model = DecisionTreeClassifier(
                max_depth=8,
                random_state=42,
                min_samples_split=5
            )
        else:  # LogisticRegression
            model = LogisticRegression(
                max_iter=200,
                random_state=42
            )
        
        model.fit(X_scaled, y)
        
        return {
            'model': model,
            'scaler': scaler,
            'training_samples': len(X)
        }
    
    @staticmethod
    def predict_congestion():
        """
        Predict current congestion risk level using trained model.
        Returns prediction with confidence score.
        """
        # Extract current features
        current_features = AICongestionPredictor.extract_features(time_window_seconds=300)
        
        # Train model if not available
        model_data = AICongestionPredictor.train_model()
        
        if model_data is None:
            # Not enough data for training, use heuristic approach
            return AICongestionPredictor._heuristic_prediction(current_features)
        
        model = model_data['model']
        scaler = model_data['scaler']
        
        # Prepare features in same format as training
        feature_dict = {
            'requests_per_second': current_features['requests_per_second'],
            'active_client_count': current_features['active_client_count'],
            'repeated_request_count': current_features['repeated_request_count'],
            'total_requests': current_features['total_requests'],
            'looping_frequency': current_features['looping_frequency'],
            'average_latency': current_features['average_latency'],
            'bandwidth_usage': current_features['bandwidth_usage'],
            'high_severity_events': current_features['high_severity_events']
        }
        
        df_features = pd.DataFrame([feature_dict])
        X_scaled = scaler.transform(df_features)
        
        # Predict
        prediction = model.predict(X_scaled)[0]
        probabilities = model.predict_proba(X_scaled)[0]
        
        # Get confidence (max probability)
        confidence = float(np.max(probabilities))
        
        return {
            'prediction': prediction,
            'confidence': confidence,
            'features': current_features,
            'model_type': AICongestionPredictor.MODEL_TYPE,
            'training_samples': model_data['training_samples'],
            'probabilities': {
                'LOW': float(probabilities[np.where(model.classes_ == AICongestionPredictor.RISK_LOW)[0][0]]) if AICongestionPredictor.RISK_LOW in model.classes_ else 0,
                'MEDIUM': float(probabilities[np.where(model.classes_ == AICongestionPredictor.RISK_MEDIUM)[0][0]]) if AICongestionPredictor.RISK_MEDIUM in model.classes_ else 0,
                'HIGH': float(probabilities[np.where(model.classes_ == AICongestionPredictor.RISK_HIGH)[0][0]]) if AICongestionPredictor.RISK_HIGH in model.classes_ else 0,
            }
        }
    
    @staticmethod
    def _heuristic_prediction(features):
        """
        Fallback heuristic prediction when insufficient training data.
        """
        active_clients = features['active_client_count']
        looping_freq = features['looping_frequency']
        request_rate = features['requests_per_second']
        avg_events = features['high_severity_events']
        
        # Calculate risk score
        risk_score = 0
        
        # Weight factors
        risk_score += (active_clients / 10) * 0.4  # Active clients weight
        risk_score += (looping_freq * 10) * 0.3   # Looping frequency weight
        risk_score += (request_rate / 50) * 0.2   # Request rate weight
        risk_score += (avg_events * 0.2) * 0.1    # Events weight
        
        if risk_score > 0.6:
            prediction = AICongestionPredictor.RISK_HIGH
            confidence = min(0.95, risk_score)
        elif risk_score > 0.35:
            prediction = AICongestionPredictor.RISK_MEDIUM
            confidence = min(0.85, risk_score)
        else:
            prediction = AICongestionPredictor.RISK_LOW
            confidence = min(0.9, 1 - risk_score)
        
        return {
            'prediction': prediction,
            'confidence': confidence,
            'features': features,
            'model_type': 'Heuristic',
            'training_samples': 0,
            'probabilities': {}
        }
    
    @staticmethod
    def get_prediction_summary():
        """
        Get comprehensive prediction summary with all details.
        """
        prediction_data = AICongestionPredictor.predict_congestion()
        features = prediction_data['features']
        
        # Determine suggested action
        prediction = prediction_data['prediction']
        if prediction == AICongestionPredictor.RISK_HIGH:
            suggested_action = "Enable load balancing, monitor connections, consider server expansion"
            self_healing_active = True
        elif prediction == AICongestionPredictor.RISK_MEDIUM:
            suggested_action = "Monitor traffic growth, prepare load balancing"
            self_healing_active = False
        else:
            suggested_action = "Network operating normally"
            self_healing_active = False
        
        summary = {
            'status': 'success',
            'prediction': prediction,
            'confidence_percentage': round(prediction_data['confidence'] * 100, 2),
            'risk_level': {
                'current': prediction,
                'low_probability': round(prediction_data['probabilities'].get('LOW', 0) * 100, 2),
                'medium_probability': round(prediction_data['probabilities'].get('MEDIUM', 0) * 100, 2),
                'high_probability': round(prediction_data['probabilities'].get('HIGH', 0) * 100, 2),
            },
            'current_metrics': {
                'active_clients': features['active_client_count'],
                'requests_per_second': round(features['requests_per_second'], 2),
                'repeated_request_count': features['repeated_request_count'],
                'total_requests': features['total_requests'],
                'looping_frequency': round(features['looping_frequency'], 3),
                'average_latency_ms': round(features['average_latency'], 2),
                'bandwidth_usage': round(features['bandwidth_usage'], 2),
                'high_severity_events': features['high_severity_events'],
                'failed_nodes': features['failed_nodes'],
            },
            'suggested_action': suggested_action,
            'self_healing_active': self_healing_active,
            'model_type': prediction_data['model_type'],
            'training_samples_used': prediction_data['training_samples'],
            'timestamp': timezone.now().isoformat()
        }
        
        return summary
