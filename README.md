# Kubernetes HPA Scanner

> Scan of a K8S cluster to identify resources/limits/ HPA not enabled. Generates PDF reports.

## Features

- ✅ Uses **official Kubernetes Python library** (`kubernetes`)
- ✅ **NO kubectl** - connects directly via API
- ✅ Shows context/cluster information
- ✅ Supports in-cluster and kubeconfig
- ✅ Automatically filters system namespaces
- ✅ **Professional PDF report generation**

## Supported Resources

- Deployments
- StatefulSets  
- ReplicaSets

## Prerequisites

1. Python 3.7+
2. Access to Kubernetes cluster (kubeconfig configured or in-cluster)
3. Permissions to list resources from apps/v1 and autoscaling/v2

## Installation

```bash
python3 -m venv k8s-hpa-scan-report
source k8s-hpa-scan-report/bin/activate
pip3 install -r requirements.txt
```
## Usage

### Basic Usage

```bash
# Run the scanner
python3 hpa-scanner.py

# Or make executable and run directly
chmod +x hpa-scanner.py
./hpa-scanner.py
```

### Advanced Usage with PDF

```bash
# Generate PDF report
export GENERATE_PDF=true
./hpa-scanner.py
```

### Configuration via File

```bash
# Edit configuration
vim .env

# Load variables and run
source .env
./hpa-scanner.py
```

## Output

The script shows:
- Resources without HPA enabled
- Grouped by namespace
- Information about replicas and resource requests
- Summary statistics

## Exit Codes

- `0`: All eligible resources have HPA enabled
- `1`: Found resources without HPA enabled

## Example Output

```
🔧 Using kubeconfig: context='my-cluster-context'
🔗 Connected to cluster: my-cluster
📋 Kubernetes version: v1.28.2

============================================================
🔍 KUBERNETES HPA SCANNER
============================================================
📡 Context: my-cluster-context
🏢 Cluster: my-cluster
👤 User: admin@my-cluster
🔧 Method: Kubernetes Python Client Library (not kubectl)
============================================================
🔍 Scanning cluster for resources without HPA...
📊 Fetching HPA resources...
📊 Fetching Deployments...
📊 Fetching StatefulSets...
📊 Fetching ReplicaSets...
📊 Checking Deployments...
📊 Checking StatefulSets...
📊 Checking ReplicaSets...

============================================================
📋 RESOURCES WITHOUT HPA ENABLED
============================================================
Found 3 resources without HPA:

📁 Namespace: default
  • Deployment/web-app (replicas=3, has resource requests)
  • StatefulSet/database (replicas=1, has resource requests)

📁 Namespace: production
  • Deployment/api-server (replicas=5, has resource requests)

============================================================
📈 SUMMARY
============================================================
Total Deployments: 15
Total StatefulSets: 3
Total ReplicaSets: 8
Resources without HPA: 3

⚠️  Consider enabling HPA for the resources listed above.
```

## Advanced Features

### 📄 PDF Reports

The script can generate professional PDF reports with:
- Cluster and context information
- Summary statistics
- Detailed list of resources without HPA
- Best practices recommendations

### 🔧 Configuration

Available environment variables:
- `GENERATE_PDF`: Generate PDF report (true/false)

## PDF Report Example

The generated PDF includes:
- Header with cluster information
- Statistics table
- List organized by namespace
- Best practices recommendations

## Future Improvements

- **Slack integration** for automated alerts and notifications
- **Email notifications** for scan results
- **Webhook support** for integration with other tools
- **Custom metrics** for HPA recommendations
- **Scheduled scanning** with cron job support
