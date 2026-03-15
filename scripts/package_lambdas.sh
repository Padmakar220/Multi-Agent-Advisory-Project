#!/bin/bash
# Package Lambda functions and layers for deployment
# Usage: ./scripts/package_lambdas.sh [--env dev|staging|prod] [--bucket BUCKET_NAME]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ENVIRONMENT="dev"
BUCKET_NAME=""
BUILD_DIR="build"
LAYERS_DIR="${BUILD_DIR}/layers"
PACKAGES_DIR="${BUILD_DIR}/packages"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --env) ENVIRONMENT="$2"; shift ;;
        --bucket) BUCKET_NAME="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

if [ -z "${BUCKET_NAME}" ]; then
    echo -e "${RED}Error: --bucket is required${NC}"
    echo "Usage: $0 --env dev --bucket my-deployment-bucket"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Packaging Lambda Functions and Layers${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Environment: ${ENVIRONMENT}"
echo "Bucket: ${BUCKET_NAME}"
echo ""

mkdir -p "${LAYERS_DIR}" "${PACKAGES_DIR}"

# ─── Build Lambda Layers ────────────────────────────────────────────────────

build_core_layer() {
    echo -e "${YELLOW}Building core-dependencies layer...${NC}"
    local layer_dir="${LAYERS_DIR}/core-dependencies/python"
    mkdir -p "${layer_dir}"

    pip install \
        "boto3>=1.34.72" \
        "botocore>=1.34.72" \
        "pydantic==2.5.3" \
        "pydantic-settings==2.1.0" \
        "aws-lambda-powertools==2.31.0" \
        "python-dateutil==2.8.2" \
        "requests==2.31.0" \
        --target "${layer_dir}" \
        --quiet \
        --upgrade

    # Remove test files and __pycache__ to reduce size
    find "${layer_dir}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${layer_dir}" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find "${layer_dir}" -name "*.pyc" -delete 2>/dev/null || true
    find "${layer_dir}" -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

    (cd "${LAYERS_DIR}/core-dependencies" && zip -r "../../${LAYERS_DIR}/core-dependencies.zip" python/ -q)
    echo -e "${GREEN}✓ core-dependencies layer built${NC}"
}

build_langgraph_layer() {
    echo -e "${YELLOW}Building langgraph layer...${NC}"
    local layer_dir="${LAYERS_DIR}/langgraph-dependencies/python"
    mkdir -p "${layer_dir}"

    pip install \
        "langgraph==0.0.26" \
        "langchain==0.1.4" \
        "langchain-aws==0.1.0" \
        --target "${layer_dir}" \
        --quiet \
        --upgrade

    find "${layer_dir}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${layer_dir}" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
    find "${layer_dir}" -name "*.pyc" -delete 2>/dev/null || true

    (cd "${LAYERS_DIR}/langgraph-dependencies" && zip -r "../../${LAYERS_DIR}/langgraph-dependencies.zip" python/ -q)
    echo -e "${GREEN}✓ langgraph layer built${NC}"
}

build_shared_code_layer() {
    echo -e "${YELLOW}Building shared-code layer...${NC}"
    local layer_dir="${LAYERS_DIR}/shared-code/python"
    mkdir -p "${layer_dir}"

    # Copy src/ package into the layer
    cp -r src/ "${layer_dir}/src"
    find "${layer_dir}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "${layer_dir}" -name "*.pyc" -delete 2>/dev/null || true

    (cd "${LAYERS_DIR}/shared-code" && zip -r "../../${LAYERS_DIR}/shared-code.zip" python/ -q)
    echo -e "${GREEN}✓ shared-code layer built${NC}"
}

# ─── Package Individual Lambda Functions ────────────────────────────────────

LAMBDA_FUNCTIONS=(
    "supervisor-agent"
    "portfolio-analyzer"
    "tax-optimizer"
    "rebalancing-agent"
    "approval-handler"
    "trade-executor"
    "portfolio-updater"
    "market-data-ingestion"
    "request-queue-handler"
)

package_lambda() {
    local fn_name="$1"
    local fn_dir="lambda/${fn_name}"

    if [ ! -d "${fn_dir}" ]; then
        echo -e "${YELLOW}⚠ Skipping ${fn_name} - directory not found${NC}"
        return
    fi

    echo -e "${YELLOW}Packaging ${fn_name}...${NC}"
    local pkg_file="${PACKAGES_DIR}/${fn_name}.zip"

    # Package only the handler and any function-local modules
    (cd "${fn_dir}" && zip -r "../../${pkg_file}" . -q \
        --exclude "*.pyc" \
        --exclude "__pycache__/*" \
        --exclude "tests/*" \
        --exclude "*.test.py")

    local size
    size=$(du -sh "${pkg_file}" | cut -f1)
    echo -e "${GREEN}✓ ${fn_name} packaged (${size})${NC}"
}

# ─── Upload to S3 ────────────────────────────────────────────────────────────

upload_to_s3() {
    echo ""
    echo -e "${YELLOW}Uploading layers to S3...${NC}"
    for zip_file in "${LAYERS_DIR}"/*.zip; do
        local key="layers/$(basename "${zip_file}")"
        aws s3 cp "${zip_file}" "s3://${BUCKET_NAME}/${key}" --quiet
        echo -e "${GREEN}✓ Uploaded ${key}${NC}"
    done

    echo ""
    echo -e "${YELLOW}Uploading Lambda packages to S3...${NC}"
    for zip_file in "${PACKAGES_DIR}"/*.zip; do
        local fn_name
        fn_name=$(basename "${zip_file}" .zip)
        local key="lambda/${fn_name}/${ENVIRONMENT}/function.zip"
        aws s3 cp "${zip_file}" "s3://${BUCKET_NAME}/${key}" --quiet
        echo -e "${GREEN}✓ Uploaded ${key}${NC}"
    done

    echo ""
    echo -e "${YELLOW}Uploading CloudFormation templates to S3...${NC}"
    for template in infrastructure/*.yaml; do
        local key="infrastructure/$(basename "${template}")"
        aws s3 cp "${template}" "s3://${BUCKET_NAME}/${key}" --quiet
        echo -e "${GREEN}✓ Uploaded ${key}${NC}"
    done
}

# ─── Main ────────────────────────────────────────────────────────────────────

build_core_layer
build_langgraph_layer
build_shared_code_layer

for fn in "${LAMBDA_FUNCTIONS[@]}"; do
    package_lambda "${fn}"
done

upload_to_s3

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ All packages uploaded to s3://${BUCKET_NAME}${NC}"
echo -e "${GREEN}========================================${NC}"
