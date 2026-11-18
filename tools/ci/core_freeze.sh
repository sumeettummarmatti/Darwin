#!/bin/sh
# core/ freeze check (PLAN.md task 1.10). A PR labelled `service-line` may not touch core/.
# Usage in CI: BASE=origin/main LABELS="service-line,…" tools/ci/core_freeze.sh
set -e
BASE="${BASE:-origin/main}"
case ",${LABELS}," in
  *,service-line,*) ;;
  *) echo "not a service-line PR — core/ freeze not enforced"; exit 0 ;;
esac
CHANGED=$(git diff --name-only "$BASE"...HEAD -- core/ || true)
if [ -n "$CHANGED" ]; then
  echo "✗ service-line PR touches the frozen kernel:"; echo "$CHANGED"
  echo "  If this is a genuine kernel finding, open a separate core PR and explain it."
  exit 1
fi
echo "✓ no files in core/ changed"
