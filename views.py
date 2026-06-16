from django.urls import path
from . import views
from . import network_api_views

app_name = 'admin_panel'

urlpatterns = [
    path('', views.admin_login, name='admin_login'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('clients/', views.admin_clients, name='admin_clients'),
    path('clients/clear/', views.admin_clients, name='admin_clear_clients'),
    path('network-monitoring/', views.admin_network_monitoring, name='admin_network_monitoring'),
    path('network-logs/', views.admin_network_logs, name='admin_network_logs'),
    path('network-monitoring-dashboard/', network_api_views.network_monitoring_dashboard, name='network_monitoring'),
    path('traffic/', views.admin_traffic, name='admin_traffic'),
    path('client-node-monitoring/', views.client_node_failure_monitoring, name='client_node_monitoring'),
    # Network Topology Visualization Route
    path('network-topology/', views.network_topology_visualization, name='network_topology_visualization'),
    # NEW: AI Analysis Panel Route
    path('ai-analysis/', views.ai_analysis_panel, name='ai_analysis_panel'),
    # NEW: Self-Healing Timeline Route
    path('self-healing-timeline/', views.self_healing_timeline, name='self_healing_timeline'),
    # API Endpoints
    path('api/dashboard/', views.api_dashboard_data, name='api_dashboard_data'),
    path('api/traffic/', views.api_traffic_data, name='api_traffic_data'),
    path('api/resolve/<int:event_id>/', views.api_resolve_event, name='api_resolve_event'),
    path('api/network-health/', network_api_views.api_network_health, name='api_network_health'),
    path('api/network-issues/', network_api_views.api_network_issues, name='api_network_issues'),
    path('api/server-nodes/', network_api_views.api_server_nodes_status, name='api_server_nodes_status'),
    path('api/connected-pcs/', network_api_views.api_connected_pcs, name='api_connected_pcs'),
    path('api/resolve-issue/', network_api_views.api_resolve_network_issue, name='api_resolve_issue'),
    path('api/client-node-status/', views.api_client_node_status, name='api_client_node_status'),
    path('api/looping-detection/', network_api_views.api_looping_detection, name='api_looping_detection'),
    path('api/looping-timeline/', network_api_views.api_looping_timeline, name='api_looping_timeline'),
    path('api/looping-statistics/', network_api_views.api_looping_statistics, name='api_looping_statistics'),
    path('api/ai-congestion-prediction/', network_api_views.api_ai_congestion_prediction, name='api_ai_congestion_prediction'),
    path('api/ai-prediction-details/', network_api_views.api_ai_prediction_details, name='api_ai_prediction_details'),
    # Network Topology API Endpoints (Real-Time Data)
    path('api/network-topology/', network_api_views.api_network_topology, name='api_network_topology'),
    path('api/network-topology-stats/', network_api_views.api_network_topology_stats, name='api_network_topology_stats'),
    # NEW: Explainable AI Analysis API Endpoint
    path('api/explainable-ai-analysis/', network_api_views.api_explainable_ai_analysis, name='api_explainable_ai_analysis'),
    # NEW: Self-Healing Timeline API Endpoint
    path('api/self-healing-events/', views.api_self_healing_events, name='api_self_healing_events'),
]
