# Improvement Roadmap - Zoom-Telebot SOC

This document outlines prioritized tasks to further enhance the codebase quality, testing, and performance.

## 1. Automated Testing Suite Expansion
**Issue**: Limited automated tests for complex FSM flows.
**Priority**: 🟠 HIGH
**Impact**: High
**Effort**: Medium
**Current State**: Basic import and integration tests in `tests/`.
**Recommended Solution**: Implement a full testing suite using `pytest` and `pytest-asyncio`.
**Implementation Steps**:
1.  Initialize `pytest` configuration and `tests/conftest.py`.
2.  Mock Telegram Bot API using `aiogram.test_utils`.
3.  Write unit tests for state transitions in `bot/handlers.py`.
4.  Mock Zoom API responses in `zoom/zoom.py` tests.

## 2. Shared Database Migration Lock
**Issue**: Risk of database corruption or locks during concurrent migration and bot startup.
**Priority**: 🟡 MEDIUM
**Impact**: Medium
**Effort**: Low
**Current State**: `init_db` runs on every startup; manual script exists.
**Recommended Solution**: Add a file-based lock or a `migration_meta` table to track migration status.
**Implementation Steps**:
1.  Add `migrations` table to track applied versions.
2.  Implement a lock mechanism in `db/db.py`'s `run_migrations`.

## 3. Log Rotation and Cleanup
**Issue**: Log files are created daily but no automated cleanup or rotation is enforced.
**Priority**: 🟡 MEDIUM
**Impact**: Low
**Effort**: Low
**Current State**: New log file created per day in `logs/`.
**Recommended Solution**: Use `logging.handlers.TimedRotatingFileHandler` or a script to purge logs > 30 days.
**Implementation Steps**:
1.  Update `bot/main.py` to use `TimedRotatingFileHandler`.
2.  Configure retention policy in `.env`.

## 4. Documentation Enrichment
**Issue**: Newer modules have inconsistent docstring detail.
**Priority**: 🟢 LOW
**Impact**: Medium
**Effort**: Low
**Current State**: Most core files are well-documented, but some helpers are sparse.
**Recommended Solution**: Perform a documentation sweep across `bot/cloud_recording_handlers.py` and `db/db.py`.
**Implementation Steps**:
1.  Standardize on Google or NumPy style docstrings for all public functions.
