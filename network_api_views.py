# This file contains additional network monitoring API URLs
# To include these URLs, add this line to cn_project/urls.py:
#     path('admin-panel/api/', include('admin_panel.network_api_urls')),

from django.urls import path
from . import network_api_views

urlpatterns = [
    path('network-health/', network_api_views.api_network_health, name='api_network_health'),
    path('network-issues/', network_api_views.api_network_issues, name='api_network_issues'),
    path('load-balance/', network_api_views.api_load_balance, name='api_load_balance'),
    path('server-nodes/', network_api_views.api_server_nodes_status, name='api_server_nodes_status'),
    path('resolve-issue/', network_api_views.api_resolve_network_issue, name='api_resolve_issue'),
]
