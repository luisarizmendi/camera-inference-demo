#!/usr/bin/env bash
set -e

# --- Defaults ---
REGISTRY=""

# --- Parse args (extract registry, forward everything) ---
FORWARD_ARGS=()

while [[ $# -gt 0 ]]; do
  case $1 in
    --registry)
      REGISTRY="$2"
      FORWARD_ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      # Forward ALL other args transparently
      FORWARD_ARGS+=("$1")
      shift
      ;;
  esac
done

echo "========================================"
echo "Running all build.sh scripts"
[[ -n "$REGISTRY" ]] && echo "Registry override: ${REGISTRY}"
echo "Args: ${FORWARD_ARGS[*]}"
echo "========================================"
echo ""

# --- Helper function to run builds in a directory ---
run_builds_in_dir() {
  local base_dir=$1

  for dir in "$base_dir"/*/ ; do
    # Skip if no match
    [[ -d "$dir" ]] || continue

    dir="${dir%/}"

    if [[ -f "${dir}/build.sh" ]]; then
      echo "========================================"
      echo "→ Running build in: ${dir}"
      echo "========================================"

      (
        cd "$dir"
        chmod +x build.sh
        ./build.sh "${FORWARD_ARGS[@]}"
      )

      echo ""
    fi
  done
}

# --- 1. Build bases first ---
if [[ -d "_bases_" ]]; then
  echo "########################################"
  echo "### Building base images first (_bases_)"
  echo "########################################"
  echo ""

  run_builds_in_dir "_bases_"
fi

# --- 2. Build all other first-level directories ---
echo "########################################"
echo "### Building remaining images"
echo "########################################"
echo ""

for dir in */ ; do
  dir="${dir%/}"

  # Skip _bases_ and non-directories
  [[ "$dir" == "_bases_" ]] && continue

  if [[ -f "${dir}/build.sh" ]]; then
    echo "========================================"
    echo "→ Running build in: ${dir}"
    echo "========================================"

    (
      cd "$dir"
      chmod +x build.sh
      ./build.sh "${FORWARD_ARGS[@]}"
    )

    echo ""
  fi
done

echo "========================================"
echo "✅ All builds completed"
echo "========================================"
