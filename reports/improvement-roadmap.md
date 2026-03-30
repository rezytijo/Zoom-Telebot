# Improvement Roadmap & Priorities

## Issue Priority Format
🔴 **CRITICAL**: Security vulnerabilities, data loss risks
🟠 **HIGH**: Code smells, missing error handling
🟡 **MEDIUM**: Code duplication, outdated dependencies
🟢 **LOW**: Formatting issues, missing comments

### 🔴 CRITICAL
None detected during initial static analysis. Credentials (`API Keys`, `tokens`, etc.) are secured in `.env` based on standard `os.getenv` usage context.

### 🟠 HIGH
1. **Unpinned Dependencies**
   - **Impact**: High (risks build failure or runtime errors due to unexpected API changes in updated packages).
   - **Effort**: Low
   - **State**: The `requirements.txt` lacks explicit versioning blocks (`aiogram`, `python-dotenv`, etc.).
   - **Solution**: Resolve current valid library versions, test, and pin them (e.g., `aiogram==3.15.0`). 
   - **Steps**:
     1. Analyze currently running package versions in testing/staging.
     2. Update to latest stable APIs (e.g. `pip install -U`).
     3. Lock `requirements.txt`.

### 🟡 MEDIUM
1. **Test Coverage**
   - **Impact**: Medium
   - **Effort**: High
   - **State**: Currently limited tests provided (`pytest_output.txt` shows minimal testing of `bot/`).
   - **Solution**: Increase coverage, especially on `bot/handlers.py` logic and FSM transitions.
   - **Steps**:
     1. Set up more `pytest-asyncio` fixtures for mocked `aiogram.types.Message`.
     2. Execute tests for core meeting creation/management loops.

### 🟢 LOW
1. **Migration Schema Versioning**
   - **Impact**: Low
   - **Effort**: Medium
   - **State**: Custom script approach for SQLite `run_migrations`.
   - **Solution**: Consider `Alembic` if moving to a more formalized ORM.
