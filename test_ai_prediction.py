#!/usr/bin/env python
"""
Test script for AI Congestion Prediction System
Demonstrates the AI module's capabilities and trains on real network data
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cn_project.settings')
django.setup()

from network_sim.ai_congestion_predictor import AICongestionPredictor
from django.utils import timezone
from datetime import timedelta


def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*90}")
    print(f"{text.center(90)}")
    print(f"{'='*90}\n")


def test_feature_extraction():
    """Test 1: Extract features from real network data"""
    print_header("TEST 1: FEATURE EXTRACTION")
    
    print("Extracting features from real network data...")
    features = AICongestionPredictor.extract_features(time_window_seconds=300)
    
    print("\n📊 Extracted Features (5-minute window):")
    print(f"  • Active Clients: {features['active_client_count']}")
    print(f"  • Requests/Second: {features['requests_per_second']:.2f}")
    print(f"  • Total Requests: {features['total_requests']}")
    print(f"  • Repeated Request Count: {features['repeated_request_count']}")
    print(f"  • Looping Frequency: {features['looping_frequency']:.3f}")
    print(f"  • Average Latency (ms): {features['average_latency']:.2f}")
    print(f"  • Bandwidth Usage: {features['bandwidth_usage']:.2f}")
    print(f"  • Connection Growth Rate: {features['connection_growth']:.2f}")
    print(f"  • High Severity Events: {features['high_severity_events']}")
    print(f"  • Failed Nodes: {features['failed_nodes']}")
    
    return features


def test_label_generation():
    """Test 2: Generate training labels from real events"""
    print_header("TEST 2: TRAINING LABEL GENERATION")
    
    print("Generating labels from historical network events...")
    training_data = AICongestionPredictor.generate_labels_for_training()
    
    print(f"\n📈 Generated {len(training_data)} training data points from last 3 hours:")
    
    if training_data:
        for i, data in enumerate(training_data, 1):
            print(f"  {i}. Time: {data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"     Label: {data['label']} | Requests: {data['request_count']} | Avg Connections: {data['avg_connections']:.1f}")
    else:
        print("  ⚠️  No training data available yet")
    
    return training_data


def test_dataset_building():
    """Test 3: Build complete training dataset"""
    print_header("TEST 3: TRAINING DATASET BUILDING")
    
    print("Building training dataset from historical data...")
    X, y = AICongestionPredictor.build_training_dataset()
    
    if X is not None:
        print(f"\n✅ Dataset built successfully!")
        print(f"  • Samples: {len(X)}")
        print(f"  • Features: {X.shape[1]}")
        print(f"\n📊 Label distribution:")
        
        unique, counts = np.unique(y, return_counts=True)
        for label, count in zip(unique, counts):
            percentage = (count / len(y)) * 100
            print(f"  • {label}: {count} samples ({percentage:.1f}%)")
    else:
        print(f"\n⚠️  Insufficient data for training")
        print(f"   Required: {AICongestionPredictor.MIN_SAMPLES_FOR_TRAINING} samples")
    
    return X, y


def test_model_training():
    """Test 4: Train the prediction model"""
    print_header("TEST 4: MODEL TRAINING")
    
    print(f"Training {AICongestionPredictor.MODEL_TYPE} model...")
    model_data = AICongestionPredictor.train_model()
    
    if model_data:
        print(f"\n✅ Model trained successfully!")
        print(f"  • Model Type: {AICongestionPredictor.MODEL_TYPE}")
        print(f"  • Training Samples: {model_data['training_samples']}")
        print(f"  • Scaler: StandardScaler (features normalized)")
    else:
        print(f"\n⚠️  Model training failed")
        print(f"   Reason: Insufficient training data")
    
    return model_data


def test_prediction():
    """Test 5: Make predictions on current data"""
    print_header("TEST 5: CONGESTION PREDICTION")
    
    print("Making congestion prediction on current network state...")
    prediction_data = AICongestionPredictor.predict_congestion()
    
    print(f"\n🎯 Prediction Result:")
    print(f"  • Risk Level: {prediction_data['prediction']}")
    print(f"  • Confidence: {prediction_data['confidence']*100:.1f}%")
    print(f"  • Model Type: {prediction_data['model_type']}")
    print(f"  • Training Samples Used: {prediction_data['training_samples']}")
    
    if prediction_data['probabilities']:
        print(f"\n📊 Risk Probabilities:")
        for risk_level in ['LOW', 'MEDIUM', 'HIGH']:
            prob = prediction_data['probabilities'].get(risk_level, 0)
            bar = '█' * int(prob * 50)
            print(f"  {risk_level:6s}: {bar:50s} {prob*100:5.1f}%")
    
    print(f"\n📈 Current Metrics (5-minute window):")
    features = prediction_data['features']
    print(f"  • Active Clients: {features['active_client_count']}")
    print(f"  • Requests/Second: {features['requests_per_second']:.2f}")
    print(f"  • Looping Frequency: {features['looping_frequency']:.3f}")
    print(f"  • Total Requests: {features['total_requests']}")
    
    return prediction_data


def test_prediction_summary():
    """Test 6: Get comprehensive prediction summary"""
    print_header("TEST 6: COMPREHENSIVE PREDICTION SUMMARY")
    
    print("Generating complete prediction summary...")
    summary = AICongestionPredictor.get_prediction_summary()
    
    print(f"\n✅ PREDICTION SUMMARY")
    print(f"  • Status: {summary['status']}")
    print(f"  • Prediction: {summary['prediction']}")
    print(f"  • Confidence: {summary['confidence_percentage']}%")
    print(f"  • Suggested Action: {summary['suggested_action']}")
    print(f"  • Self-Healing Active: {'🟢 YES' if summary['self_healing_active'] else '🔵 NO'}")
    
    print(f"\n📊 Current Metrics:")
    metrics = summary['current_metrics']
    print(f"  • Active Clients: {metrics['active_clients']}/{metrics['active_clients_threshold']}")
    print(f"  • Active Clients %: {metrics['active_clients_percentage']:.1f}%")
    print(f"  • Requests/Second: {metrics['requests_per_second']:.2f}")
    print(f"  • Total Requests: {metrics['total_requests']}")
    print(f"  • Repeated Request Count: {metrics['repeated_request_count']}")
    print(f"  • Looping Frequency: {metrics['looping_frequency']:.3f}")
    print(f"  • Avg Latency: {metrics['average_latency_ms']:.2f}ms")
    print(f"  • High Severity Events: {metrics['high_severity_events']}")
    print(f"  • Failed Nodes: {metrics['failed_nodes']}")
    
    print(f"\n🎯 Risk Level Breakdown:")
    risk = summary['risk_level']
    print(f"  • LOW: {risk['low_probability']}%")
    print(f"  • MEDIUM: {risk['medium_probability']}%")
    print(f"  • HIGH: {risk['high_probability']}%")
    
    return summary


def main():
    """Run all tests"""
    print("\n")
    print("█" * 90)
    print("AI-BASED CONGESTION PREDICTION SYSTEM - TEST SUITE".center(90))
    print("█" * 90)
    
    try:
        # Test feature extraction
        test_feature_extraction()
        
        # Test label generation
        test_label_generation()
        
        # Test dataset building
        test_dataset_building()
        
        # Test model training
        test_model_training()
        
        # Test prediction
        test_prediction()
        
        # Test summary
        test_prediction_summary()
        
        print_header("ALL TESTS COMPLETED SUCCESSFULLY ✅")
        
        print("\n📌 USAGE EXAMPLES:\n")
        
        print("1️⃣  Quick Prediction:")
        print("""
from network_sim.ai_congestion_predictor import AICongestionPredictor

prediction = AICongestionPredictor.predict_congestion()
print(f"Risk Level: {prediction['prediction']}")
print(f"Confidence: {prediction['confidence']*100:.1f}%")
        """)
        
        print("\n2️⃣  Get Full Summary (Recommended):")
        print("""
summary = AICongestionPredictor.get_prediction_summary()
print(f"Prediction: {summary['prediction']}")
print(f"Action: {summary['suggested_action']}")
        """)
        
        print("\n3️⃣  Extract Features Manually:")
        print("""
features = AICongestionPredictor.extract_features(time_window_seconds=300)
print(f"Active Clients: {features['active_client_count']}")
        """)
        
        print("\n4️⃣  Via API Endpoints:")
        print("""
GET /admin-panel/api/ai-congestion-prediction/
GET /admin-panel/api/ai-prediction-details/
        """)
        
    except Exception as e:
        print_header("TEST FAILED WITH ERROR ❌")
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import numpy as np
    main()
