#!/usr/bin/env bash
#
# Point a production tag at a specific release tag and push it.
# This local script exists because the shared ci-helpers auto-tag workflow
# expects `./scripts/create_production.sh` in the target repository.

set -euo pipefail

tag=""
prod_tag="production"
remote="origin"
repo_dir="${GITHUB_WORKSPACE:-$(pwd)}"
fetch_tags=false

usage() {
  cat <<'EOF'
Usage: ./scripts/create_production.sh -t <tag> [--name <name>] [--remote <name>] [--repo <path>] [--fetch-tags]

Options:
  -t, --tag <tag>       Release tag to point the production tag at (required)
  --name <name>         Production tag name (default: production)
  --remote <name>       Remote to push to (default: origin)
  --repo <path>         Repository path (default: current workspace)
  --fetch-tags          Fetch tags before updating
  -h, --help            Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--tag)
      tag="${2:-}"
      shift 2
      ;;
    --name|--tag-name|--branch)
      prod_tag="${2:-}"
      shift 2
      ;;
    --remote)
      remote="${2:-}"
      shift 2
      ;;
    --repo)
      repo_dir="${2:-}"
      shift 2
      ;;
    --fetch-tags)
      fetch_tags=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$tag" ]]; then
  echo "Error: missing required -t|--tag" >&2
  usage >&2
  exit 2
fi

if [[ ! -d "$repo_dir/.git" ]]; then
  echo "Error: repo path is not a git repository: $repo_dir" >&2
  exit 1
fi

if $fetch_tags; then
  git -C "$repo_dir" fetch --tags --prune --force >/dev/null 2>&1 || true
fi

if ! git -C "$repo_dir" rev-parse "refs/tags/$tag" >/dev/null 2>&1; then
  echo "Error: tag '$tag' not found in $repo_dir" >&2
  exit 1
fi

echo "Updating tag '$prod_tag' -> '$tag'"
git -C "$repo_dir" tag -f "$prod_tag" "$tag"
git -C "$repo_dir" push "$remote" "refs/tags/${prod_tag}:refs/tags/${prod_tag}" --force-with-lease
echo "Tag '$prod_tag' now points to '$tag'"
