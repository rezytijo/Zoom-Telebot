# Makefile for Zoom-Telebot SOC Docker Management

.PHONY: help build up down restart logs clean backup restore dev prod test

# Default target
help: ## Show this help message
	@echo "🤖 Zoom-Telebot SOC Docker Management"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Development commands
dev-build: ## Build development image
	docker compose build zoom-telebot-dev

dev-up: ## Start development environment
	docker compose --profile dev up zoom-telebot-dev

dev-down: ## Stop development environment
	docker compose --profile dev down

dev-logs: ## Show development logs
	docker compose --profile dev logs -f zoom-telebot-dev

dev-restart: ## Restart development environment
	docker compose --profile dev restart zoom-telebot-dev

# Production commands
prod-build: ## Build production image
	docker compose -f docker-compose.yml -f docker-compose.prod.yml build

prod-up: ## Start production environment
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-down: ## Stop production environment
	docker compose -f docker-compose.yml -f docker-compose.prod.yml down

prod-logs: ## Show production logs
	docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f

prod-restart: ## Restart production environment
	docker compose -f docker-compose.yml -f docker-compose.prod.yml restart

# General commands
build: ## Build default image
	docker compose build

up: ## Start services
	docker compose up -d

down: ## Stop services
	docker compose down

restart: ## Restart services
	docker compose restart

logs: ## Show logs
	docker compose logs -f

status: ## Show service status
	docker compose ps

# Maintenance commands
clean: ## Remove containers, networks, and images
	docker compose down --rmi all --volumes --remove-orphans

clean-logs: ## Clean log files
	sudo rm -rf logs/*.log

migrate: ## Run database migrations (production)
	@echo "🔄 Running database migrations..."
	docker compose exec zoom-telebot python scripts/run_migration.py
	@echo "✅ Migration complete. Restart bot to apply changes: make restart"

migrate-dev: ## Run database migrations (development)
	@echo "🔄 Running database migrations (dev)..."
	docker compose --profile dev exec zoom-telebot-dev python scripts/run_migration.py
	@echo "✅ Migration complete. Restart bot to apply changes: make dev-restart"

migrate-local: ## Run database migrations (local/no Docker)
	@echo "🔄 Running database migrations (local)..."
	python scripts/run_migration.py
	@echo "✅ Migration complete. Restart bot to apply changes."

db-check: ## Check database schema
	@echo "📊 Checking database schema..."
	docker compose exec zoom-telebot sqlite3 /app/zoom_telebot.db "PRAGMA table_info(meetings);"
	@echo ""
	docker compose exec zoom-telebot sqlite3 /app/zoom_telebot.db "PRAGMA table_info(meeting_live_status);"

backup: ## Create database backup
	@echo "Creating backup..."
	@mkdir -p backups
	@cp data/zoom_telebot.db backups/zoom_telebot_$(shell date +%Y%m%d_%H%M%S).db
	@echo "Backup created in backups/"

backup-docker: ## Create backup using Docker
	docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile backup run --rm backup-service

restore: ## Restore database from backup (usage: make restore FILE=backup_file.db)
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make restore FILE=backup_file.db"; \
		exit 1; \
	fi
	@echo "Restoring from $(FILE)..."
	@cp backups/$(FILE) data/zoom_telebot.db
	@echo "Database restored"

# Testing commands
test: ## Run tests in container
	docker compose run --rm zoom-telebot python dev.py test

test-build: ## Test build process
	docker compose build --no-cache

test-run: ## Run tests using test profile
	docker compose --profile test up --abort-on-container-exit --exit-code-from zoom-telebot-test

test-clean: ## Clean test environment
	docker compose --profile test down --volumes --remove-orphans

# Utility commands
shell: ## Open shell in running container
	docker compose exec zoom-telebot /bin/bash

shell-dev: ## Open shell in development container
	docker compose --profile dev exec zoom-telebot-dev /bin/bash

env-check: ## Check environment configuration
	docker compose run --rm zoom-telebot python dev.py check

setup: ## Run setup in container
	docker compose run --rm zoom-telebot python setup.py

# Docker system commands
docker-clean: ## Clean up Docker system
	docker system prune -f
	docker volume prune -f

docker-logs: ## Show all Docker logs
	docker compose logs --tail=100

# Information commands
info: ## Show system information
	@echo "=== Docker Information ==="
	docker --version
	docker compose version
	@echo ""
	@echo "=== Container Status ==="
	docker compose ps
	@echo ""
	@echo "=== Volume Status ==="
	docker volume ls | grep zoom
	@echo ""
	@echo "=== Image Status ==="
	docker images | grep zoom

version: ## Show version information
	@echo "Zoom-Telebot SOC"
	@echo "Docker Configuration"
	@git log --oneline -1 2>/dev/null || echo "Git not available"