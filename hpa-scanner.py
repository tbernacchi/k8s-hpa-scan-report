#!/usr/bin/env python3
"""
Kubernetes HPA Scanner
Scans the cluster for resources that can use HPA and identifies which ones don't have HPA enabled.
Uses the official Kubernetes Python client library.
"""

import sys
import os
from datetime import datetime
from typing import List, Dict, Set, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# Global variables for API clients and cluster info
apps_v1 = None
autoscaling_v2 = None
core_v1 = None
cluster_info = {}

def initialize_kubernetes_client():
    """Initialize the Kubernetes client."""
    global apps_v1, autoscaling_v2, core_v1, cluster_info
    
    try:
        # Try to load in-cluster config first (if running inside a pod)
        config.load_incluster_config()
        cluster_info['context'] = 'in-cluster'
        print("🔧 Using in-cluster Kubernetes configuration")
    except config.ConfigException:
        try:
            # Fall back to kubeconfig file
            config.load_kube_config()
            # Get current context info
            contexts, active_context = config.list_kube_config_contexts()
            if active_context:
                cluster_info['context'] = active_context['name']
                cluster_info['cluster'] = active_context['context'].get('cluster', 'unknown')
                cluster_info['user'] = active_context['context'].get('user', 'unknown')
            else:
                cluster_info['context'] = 'unknown'
            print(f"🔧 Using kubeconfig: context='{cluster_info['context']}'")
        except config.ConfigException as e:
            print(f"❌ Error loading Kubernetes config: {e}")
            sys.exit(1)
    
    # Initialize API clients
    apps_v1 = client.AppsV1Api()
    autoscaling_v2 = client.AutoscalingV2Api()
    core_v1 = client.CoreV1Api()
    
    # Test connectivity and get cluster info
    get_cluster_info()

def get_cluster_info():
    """Get cluster information and test connectivity."""
    global cluster_info
    
    try:
        # Test connectivity by listing namespaces (simple and reliable)
        namespaces = core_v1.list_namespace()
        namespace_count = len(namespaces.items) if namespaces.items else 0
        
        print(f"🔗 Connected to cluster: {cluster_info.get('cluster', 'unknown')}")
        print(f"📋 Found {namespace_count} namespaces")
        
        # Try to get version info if possible
        try:
            version_info = core_v1.get_code()
            if hasattr(version_info, 'git_version'):
                cluster_info['version'] = version_info.git_version
                print(f"📋 Kubernetes version: {cluster_info['version']}")
            else:
                cluster_info['version'] = 'unknown'
        except (ApiException, AttributeError):
            cluster_info['version'] = 'unknown'
            print(f"📋 Kubernetes version: {cluster_info['version']}")
        
    except ApiException as e:
        print(f"❌ Error connecting to cluster: {e}")
        sys.exit(1)

def get_hpa_resources() -> Set[str]:
    """Get all HPA resources and return a set of their target resource names."""
    hpa_targets = set()
    
    try:
        # Get all HPAs across all namespaces
        hpa_list = autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces()
        
        for hpa in hpa_list.items:
            if hpa.spec and hpa.spec.scale_target_ref:
                name = hpa.spec.scale_target_ref.name
                kind = hpa.spec.scale_target_ref.kind
                namespace = hpa.metadata.namespace or 'default'
                
                # Create a unique identifier for the target resource
                target_id = f"{namespace}/{kind}/{name}"
                hpa_targets.add(target_id)
                
    except ApiException as e:
        print(f"⚠️  Warning: Could not fetch HPA resources: {e}")
        
    return hpa_targets

def get_deployments() -> List[client.V1Deployment]:
    """Get all Deployments across all namespaces."""
    try:
        deployment_list = apps_v1.list_deployment_for_all_namespaces()
        return deployment_list.items
    except ApiException as e:
        print(f"❌ Error fetching Deployments: {e}")
        return []

def get_statefulsets() -> List[client.V1StatefulSet]:
    """Get all StatefulSets across all namespaces."""
    try:
        statefulset_list = apps_v1.list_stateful_set_for_all_namespaces()
        return statefulset_list.items
    except ApiException as e:
        print(f"❌ Error fetching StatefulSets: {e}")
        return []

def get_replicasets() -> List[client.V1ReplicaSet]:
    """Get all ReplicaSets across all namespaces."""
    try:
        replicaset_list = apps_v1.list_replica_set_for_all_namespaces()
        return replicaset_list.items
    except ApiException as e:
        print(f"❌ Error fetching ReplicaSets: {e}")
        return []

def check_resource_for_hpa(resources: List, resource_type: str, hpa_targets: Set[str]) -> List[Dict]:
    """Check if resources have HPA enabled and return those without HPA."""
    resources_without_hpa = []
    
    for resource in resources:
        name = resource.metadata.name
        namespace = resource.metadata.namespace or 'default'
        
        # Skip system namespaces
        if namespace.startswith('kube-') or namespace.startswith('system-'):
            continue
        
        # Create target identifier
        target_id = f"{namespace}/{resource_type}/{name}"
        
        # Check if this resource has HPA
        if target_id not in hpa_targets:
            # Get replicas from spec
            replicas = 1
            if hasattr(resource.spec, 'replicas') and resource.spec.replicas:
                replicas = resource.spec.replicas
            
            # Check if the resource has resource requests/limits that would benefit from HPA
            has_resource_requests = False
            if hasattr(resource.spec, 'template') and resource.spec.template:
                template = resource.spec.template
                if hasattr(template, 'spec') and template.spec:
                    containers = template.spec.containers or []
                    for container in containers:
                        if hasattr(container, 'resources') and container.resources:
                            if container.resources.requests or container.resources.limits:
                                has_resource_requests = True
                                break
            
            # Include ONLY if it has NO resource requests/limits AND no HPA
            # (resources without resource requests are the priority for HPA)
            if not has_resource_requests:
                resources_without_hpa.append({
                    'name': name,
                    'namespace': namespace,
                    'type': resource_type,
                    'replicas': replicas,
                    'has_resource_requests': has_resource_requests
                })
    
    return resources_without_hpa

def scan_cluster():
    """Main function to scan for resources without HPA."""
    print("\n" + "=" * 60)
    print("🔍 KUBERNETES HPA SCANNER")
    print("=" * 60)
    print(f"📡 Context: {cluster_info.get('context', 'unknown')}")
    print(f"🏢 Cluster: {cluster_info.get('cluster', 'unknown')}")
    print(f"👤 User: {cluster_info.get('user', 'unknown')}")
    print(f"🔧 Method: Kubernetes Python Client Library (not kubectl)")
    print("=" * 60)
    print("🔍 Scanning cluster for resources without HPA...")
    print("💡 Looking for resources with NO resource requests/limits (priority for HPA)")
    
    # Get HPA targets first
    print("📊 Fetching HPA resources...")
    hpa_targets = get_hpa_resources()
    
    # Get all resources that can use HPA
    print("📊 Fetching Deployments...")
    deployments = get_deployments()
    
    print("📊 Fetching StatefulSets...")
    statefulsets = get_statefulsets()
    
    print("📊 Fetching ReplicaSets...")
    replicasets = get_replicasets()
    
    # Check each resource type
    all_resources_without_hpa = []
    
    print("📊 Checking Deployments...")
    deployments_without_hpa = check_resource_for_hpa(deployments, 'Deployment', hpa_targets)
    all_resources_without_hpa.extend(deployments_without_hpa)
    
    print("📊 Checking StatefulSets...")
    statefulsets_without_hpa = check_resource_for_hpa(statefulsets, 'StatefulSet', hpa_targets)
    all_resources_without_hpa.extend(statefulsets_without_hpa)
    
    print("📊 Checking ReplicaSets...")
    replicasets_without_hpa = check_resource_for_hpa(replicasets, 'ReplicaSet', hpa_targets)
    all_resources_without_hpa.extend(replicasets_without_hpa)
    
    # Display results
    print("\n" + "=" * 60)
    print("📋 RESOURCES WITHOUT HPA ENABLED")
    print("=" * 60)
    
    if not all_resources_without_hpa:
        print("✅ All eligible resources have HPA enabled!")
    else:
        print(f"Found {len(all_resources_without_hpa)} resources without HPA:")
        print()
        
        # Group by namespace
        by_namespace = {}
        for resource in all_resources_without_hpa:
            namespace = resource['namespace']
            if namespace not in by_namespace:
                by_namespace[namespace] = []
            by_namespace[namespace].append(resource)
        
        for namespace in sorted(by_namespace.keys()):
            print(f"📁 Namespace: {namespace}")
            for resource in by_namespace[namespace]:
                replicas_info = f"replicas={resource['replicas']}"
                resources_info = "has resource requests" if resource['has_resource_requests'] else "no resource requests"
                print(f"  • {resource['type']}/{resource['name']} ({replicas_info}, {resources_info})")
            print()
    
    # Summary statistics
    print("=" * 60)
    print("📈 SUMMARY")
    print("=" * 60)
    
    print(f"Total Deployments: {len(deployments)}")
    print(f"Total StatefulSets: {len(statefulsets)}")
    print(f"Total ReplicaSets: {len(replicasets)}")
    print(f"Resources without HPA: {len(all_resources_without_hpa)}")
    
    # Generate PDF report if requested
    if os.getenv('GENERATE_PDF', 'false').lower() == 'true':
        generate_pdf_report(all_resources_without_hpa, deployments, statefulsets, replicasets)
    
    
    # Exit with appropriate code
    if all_resources_without_hpa:
        print("\n⚠️  Consider enabling HPA for the resources listed above.")
        print("💡 Priority: Resources without resource requests/limits need HPA most urgently")
        return 1
    else:
        print("\n✅ All eligible resources have HPA enabled!")
        return 0

def generate_pdf_report(all_resources_without_hpa: List[Dict], deployments: List, statefulsets: List, replicasets: List, output_file: str = None):
    """Generate a PDF report with the HPA scan results."""
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"hpa-scan-report_{timestamp}.pdf"
    
    # Create PDF document
    doc = SimpleDocTemplate(output_file, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1,  # Center alignment
        textColor=colors.darkblue
    )
    story.append(Paragraph("Kubernetes HPA Scanner Report", title_style))
    story.append(Spacer(1, 12))
    
    # Report info
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(f"<b>Generated:</b> {report_date}", styles['Normal']))
    story.append(Paragraph(f"<b>Cluster:</b> {cluster_info.get('cluster', 'unknown')}", styles['Normal']))
    story.append(Paragraph(f"<b>Context:</b> {cluster_info.get('context', 'unknown')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Summary
    story.append(Paragraph("Summary", styles['Heading2']))
    summary_data = [
        ['Metric', 'Count'],
        ['Total Deployments', len(deployments)],
        ['Total StatefulSets', len(statefulsets)],
        ['Total ReplicaSets', len(replicasets)],
        ['Resources without HPA', len(all_resources_without_hpa)]
    ]
    
    # Align table with the "S" of "Summary"
    summary_table = Table(summary_data, colWidths=[3*inch, 1.5*inch], hAlign='LEFT')
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))
    
    # Resources without HPA
    if all_resources_without_hpa:
        story.append(Paragraph("Resources Without HPA", styles['Heading2']))
        
        # Group by namespace
        by_namespace = {}
        for resource in all_resources_without_hpa:
            namespace = resource['namespace']
            if namespace not in by_namespace:
                by_namespace[namespace] = []
            by_namespace[namespace].append(resource)
        
        for namespace in sorted(by_namespace.keys()):
            story.append(Paragraph(f"<b>Namespace: {namespace}</b>", styles['Heading3']))
            
            # Create table for this namespace
            table_data = [['Resource Type', 'Name', 'Replicas', 'RR']]
            for resource in by_namespace[namespace]:
                has_requests = "Yes" if resource['has_resource_requests'] else "No"
                table_data.append([
                    resource['type'],
                    resource['name'],
                    str(resource['replicas']),
                    has_requests
                ])
            
            # Adjust column widths to accommodate longer pod names
            resource_table = Table(table_data, colWidths=[1.2*inch, 3*inch, 0.8*inch, 1.2*inch])
            resource_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            story.append(resource_table)
            story.append(Spacer(1, 12))
    else:
        story.append(Paragraph("✅ All eligible resources have HPA enabled!", styles['Normal']))
    
    # Recommendations
    story.append(Spacer(1, 20))
    story.append(Paragraph("Recommendations", styles['Heading2']))
    recommendations = [
        "• Enable HPA for resources with multiple replicas to handle traffic spikes",
        "• Set resource requests/limits for resources without them to enable proper scaling",
        "• Monitor CPU and memory usage to set appropriate HPA thresholds",
        "• Consider using custom metrics for more sophisticated scaling decisions",
        "• Test HPA behavior in staging environments before production deployment"
    ]
    
    for rec in recommendations:
        story.append(Paragraph(rec, styles['Normal']))
        story.append(Spacer(1, 6))
    
    # Build PDF
    doc.build(story)
    print(f"📄 PDF report generated: {output_file}")
    return output_file


def main():
    """Main entry point."""
    try:
        # Initialize Kubernetes client
        initialize_kubernetes_client()
        
        # Scan cluster for resources without HPA
        exit_code = scan_cluster()
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
