#!/usr/bin/env bash
# Build-only pilots may use branches; publishing always requires main.
set -euo pipefail
if [ "$EVENT" = workflow_dispatch ]; then
  test "${ACTOR,,}" = "${OWNER,,}"
  test "${TRIGGERING_ACTOR,,}" = "${OWNER,,}"
  [[ "$GITHUB_REF" == refs/heads/* ]]
  case "$PUBLISH_REQUESTED" in
    false) ;;
    true) test "$GITHUB_REF" = refs/heads/main ;;
    *) echo 'Invalid publish input'; exit 1 ;;
  esac
elif [ "$EVENT" = push ]; then
  test "$GITHUB_REF" = refs/heads/main
  test "$AUTO_ENABLED" = true || { echo 'Enable ORBISDESK_AUTO_RELEASE=true after a successful manual pilot.'; exit 1; }
else
  echo 'Unsupported product workflow event'
  exit 1
fi
