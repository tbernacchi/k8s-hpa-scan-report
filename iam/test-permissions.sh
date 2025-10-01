#!/bin/bash

# Function to test permission for a resource
test_permission() {
    local resource=$1
    if kubectl auth can-i list "$resource" --all-namespaces >/dev/null 2>&1; then
        echo "✅ $resource - OK"
        return 0
    else
        echo "❌ $resource - NO PERMISSION"
        return 1
    fi
}

echo "🔍 Testing HPA Scanner permissions..."
echo "====================================="

# Test connectivity
if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "❌ No cluster connectivity"
    exit 1
fi

echo "✅ Connectivity OK"
echo ""

# Test essential permissions
echo "🔐 Testing resource permissions..."
echo "--------------------------------"

# Test each resource
resources=("deployments" "statefulsets" "replicasets" "horizontalpodautoscalers")

for resource in "${resources[@]}"; do
    if ! test_permission "$resource"; then
        exit 1
    fi
done

echo ""
echo "🎉 All permissions OK!"
echo "🚀 You can run the HPA Scanner"
