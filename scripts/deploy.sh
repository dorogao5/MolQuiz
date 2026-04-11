#!/usr/bin/env bash
set -euo pipefail

DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_APP_PULL="${DEPLOY_APP_PULL:-false}"
DEPLOY_APP_RESTART="${DEPLOY_APP_RESTART:-false}"
DEPLOY_APP_MIGRATE="${DEPLOY_APP_MIGRATE:-false}"
DEPLOY_OPSIN_PULL="${DEPLOY_OPSIN_PULL:-false}"
DEPLOY_OPSIN_RESTART="${DEPLOY_OPSIN_RESTART:-false}"
DEPLOY_APP_IMAGE="${DEPLOY_APP_IMAGE:-}"
DEPLOY_OPSIN_IMAGE="${DEPLOY_OPSIN_IMAGE:-}"
DEPLOY_STATE_FILE="${DEPLOY_STATE_FILE:-.env.deploy}"

log() {
  printf '[deploy] %s\n' "$*"
}

compose() {
  docker compose "$@"
}

require_clean_worktree() {
  if [[ -n "$(git status --porcelain)" ]]; then
    log "Refusing to deploy with local git changes on the server checkout."
    git status --short
    exit 1
  fi
}

sync_repo() {
  local current_branch

  git fetch origin --prune
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$current_branch" != "$DEPLOY_BRANCH" ]]; then
    git checkout "$DEPLOY_BRANCH"
  fi
  git pull --ff-only origin "$DEPLOY_BRANCH"
}

configure_images() {
  if [[ -f "$DEPLOY_STATE_FILE" ]]; then
    # Reuse the last deployed image refs for config-only restarts.
    set -a
    # shellcheck disable=SC1090
    source "$DEPLOY_STATE_FILE"
    set +a
  fi

  if [[ -n "$DEPLOY_APP_IMAGE" ]]; then
    export MOLQUIZ_APP_IMAGE="$DEPLOY_APP_IMAGE"
    log "Using app image $MOLQUIZ_APP_IMAGE"
  fi

  if [[ -n "$DEPLOY_OPSIN_IMAGE" ]]; then
    export MOLQUIZ_OPSIN_IMAGE="$DEPLOY_OPSIN_IMAGE"
    log "Using OPSIN image $MOLQUIZ_OPSIN_IMAGE"
  fi

  cat > "$DEPLOY_STATE_FILE" <<EOF
MOLQUIZ_APP_IMAGE=${MOLQUIZ_APP_IMAGE:-molquiz-bot}
MOLQUIZ_OPSIN_IMAGE=${MOLQUIZ_OPSIN_IMAGE:-molquiz-opsin}
EOF
}

login_registry() {
  if [[ -z "${GHCR_USERNAME:-}" || -z "${GHCR_TOKEN:-}" ]]; then
    log "Skipping GHCR login; credentials were not provided."
    return
  fi

  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin >/dev/null
  log "Authenticated to ghcr.io"
}

ensure_base_services() {
  compose up -d postgres redis
  compose up -d --no-build opsin
}

deploy_opsin() {
  if [[ "$DEPLOY_OPSIN_PULL" == "true" ]]; then
    log "Pulling updated OPSIN image"
    compose pull opsin
  fi

  if [[ "$DEPLOY_OPSIN_RESTART" == "true" ]]; then
    log "Restarting OPSIN"
    compose up -d --no-deps --no-build opsin
  fi
}

deploy_app() {
  if [[ "$DEPLOY_APP_PULL" == "true" ]]; then
    log "Pulling updated app image for bot, worker and migrate"
    compose pull bot worker migrate
  fi

  if [[ "$DEPLOY_APP_MIGRATE" == "true" ]]; then
    log "Running Alembic migrations"
    compose run --rm --no-deps migrate
  fi

  if [[ "$DEPLOY_APP_RESTART" == "true" ]]; then
    log "Restarting bot and worker"
    compose up -d --no-deps --no-build bot worker
  fi
}

main() {
  log "Starting deploy on branch $DEPLOY_BRANCH"
  require_clean_worktree
  sync_repo
  configure_images
  login_registry
  ensure_base_services
  deploy_opsin
  deploy_app
  compose ps
}

main "$@"
