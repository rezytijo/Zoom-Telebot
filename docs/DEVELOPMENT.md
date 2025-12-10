# Development Guide - Zoom-Telebot SOC

Panduan lengkap untuk development Zoom-Telebot SOC.

## 🏗️ Setup Development Environment

### Prerequisites
- Python 3.11+
- Git
- Virtual environment (recommended)
- Code editor (VS Code, PyCharm, dll.)

### Initial Setup
```bash
# Clone repository
git clone <repository-url>
cd BotTelegramZoom

# Create virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Setup development environment
cp .env.example .env
# Edit .env dengan test credentials

# Initial database setup
python scripts/setup.py
```

## 📁 Project Structure

```
BotTelegramZoom/
├── bot/                    # Core bot logic
│   ├── __init__.py
│   ├── main.py            # Bot initialization
│   ├── handlers.py        # Telegram command handlers
│   ├── keyboards.py       # Inline keyboards
│   ├── middleware.py      # Bot middleware
│   └── auth.py            # Authentication logic
├── zoom/                   # Zoom API integration
│   ├── __init__.py
│   └── zoom.py            # ZoomClient class
├── db/                     # Database layer
│   ├── __init__.py
│   └── db.py              # Database operations
├── config/                 # Configuration
│   ├── __init__.py
│   └── config.py          # Settings management
├── c2/                     # C2 Framework integration
│   ├── __init__.py
│   └── sliver_zoom_c2.py  # Sliver C2 client
├── shortener/             # URL shortener
│   ├── __init__.py
│   └── shortener.py       # Dynamic shortener
├── scripts/               # Utility scripts
│   ├── __init__.py
│   ├── setup.py          # Environment setup
│   └── dev.py            # Development helpers
├── tests/                 # Unit tests
│   └── __init__.py
├── docker/                # Docker config
├── data/                  # Persistent data
└── docs/                  # Documentation
```

## 🚀 Menjalankan dalam Development Mode

### Development Server
```bash
# Jalankan bot dalam development mode
python run.py

# Dengan debug logging
python run.py --log-level DEBUG

# Cek konfigurasi sebelum menjalankan
python run.py --check-config

# Lihat versi
python run.py --version

# Lihat semua opsi
python run.py --help

# Dengan hot reload (jika menggunakan tools seperti nodemon)
# Install nodemon globally: npm install -g nodemon
nodemon --exec python run.py
```

### Testing Commands
```bash
# Jalankan unit tests
python -m pytest tests/

# Jalankan dengan coverage
python -m pytest --cov=bot --cov-report=html tests/

# Jalankan specific test
python -m pytest tests/test_handlers.py -v
```

## 🔧 Development Workflow

### 1. Create Feature Branch
```bash
# Create new branch
git checkout -b feature/new-feature

# Work on feature
# Make changes, test, commit

# Push branch
git push origin feature/new-feature
```

### 2. Code Style
```bash
# Format code dengan black
black .

# Sort imports dengan isort
isort .

# Lint code dengan flake8
flake8 .

# Type checking dengan mypy
mypy .
```

### 3. Testing
```bash
# Run all tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=. --cov-report=term-missing

# Run specific test file
python -m pytest tests/test_specific.py -v
```

### 4. Database Development
```bash
# Reset database untuk development
rm data/zoom_telebot.db
python scripts/setup.py

# Check database schema
python -c "from db.db import init_db; import asyncio; asyncio.run(init_db())"

# View database content
sqlite3 data/zoom_telebot.db
.schema
SELECT * FROM users LIMIT 5;
```

## 📝 Adding New Features

### Menambah Command Handler
```python
# Di bot/handlers.py
from aiogram import types
from ..config import settings

async def new_command_handler(message: types.Message):
    """Handler untuk command baru"""
    await message.reply("Hello from new command!")

# Register handler di bot/main.py
dp.register_message_handler(new_command_handler, commands=['newcommand'])
```

### Menambah Database Model
```python
# Di db/db.py
CREATE_NEW_TABLE = """
CREATE TABLE IF NOT EXISTS new_feature (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Update migration function
async def migrate_database():
    async with aiosqlite.connect(settings.database_url.split('///')[-1]) as db:
        await db.execute(CREATE_NEW_TABLE)
        await db.commit()
```

### Menambah Configuration
```python
# Di config/config.py
class Settings:
    # Existing settings...

    # New setting
    new_feature_enabled: bool = Field(default=True, env="NEW_FEATURE_ENABLED")
    new_feature_timeout: int = Field(default=30, env="NEW_FEATURE_TIMEOUT")
```

### Menambah C2 Integration
```python
# Di c2/sliver_zoom_c2.py
async def new_c2_function(agent_name: str) -> Dict[str, Any]:
    """New C2 integration function"""
    # Implement new C2 functionality
    pass

# Add route
app.router.add_get('/api/new-endpoint', new_endpoint)
```

## 🔍 Debugging

### Logging
```python
import logging
logger = logging.getLogger(__name__)

async def some_function():
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
```

### Interactive Debugging
```python
# Add breakpoint
import pdb; pdb.set_trace()

# Atau menggunakan IPython
from IPython import embed; embed()
```

### Environment Variables untuk Debug
```bash
# Set debug environment
export LOG_LEVEL=DEBUG
export PYTHONPATH=/path/to/project

# Run with debug
python -m pdb run.py
```

## 🧪 Testing Strategy

### Unit Tests
```python
# tests/test_handlers.py
import pytest
from bot.handlers import some_handler

@pytest.mark.asyncio
async def test_some_handler():
    # Test code here
    assert True
```

### Integration Tests
```python
# Test dengan database
@pytest.fixture
async def db_connection():
    # Setup test database
    yield connection
    # Cleanup

@pytest.mark.asyncio
async def test_database_operation(db_connection):
    # Test database operations
    pass
```

### Mock External APIs
```python
from unittest.mock import patch, MagicMock

@patch('zoom.zoom.ZoomClient.create_meeting')
async def test_zoom_integration(mock_create_meeting):
    mock_create_meeting.return_value = {"id": "123"}
    # Test code
```

## 🚀 Deployment

### Development to Production
```bash
# Build production image
docker build --target production -t zoom-telebot:latest .

# Run production container
docker compose up -d

# Check logs
docker compose logs -f
```

### Environment Management
```bash
# Development
cp .env.example .env.dev
# Edit untuk development

# Production
cp .env.example .env.prod
# Edit untuk production
```

## 📊 Performance Monitoring

### Profiling Code
```python
import cProfile
import pstats

def profile_function():
    cProfile.run('main()', 'profile_output.prof')

    p = pstats.Stats('profile_output.prof')
    p.sort_stats('cumulative').print_stats(10)
```

### Memory Usage
```python
import psutil
import os

process = psutil.Process(os.getpid())
memory_usage = process.memory_info().rss / 1024 / 1024  # MB
print(f"Memory usage: {memory_usage:.2f} MB")
```

## 🔒 Security Best Practices

### Environment Variables
- Jangan commit `.env` files
- Gunakan strong, random secrets
- Rotate credentials regularly

### Code Security
```python
# Input validation
from pydantic import BaseModel, validator

class UserInput(BaseModel):
    username: str

    @validator('username')
    def username_must_be_valid(cls, v):
        if not v.isalnum():
            raise ValueError('Username must be alphanumeric')
        return v
```

### Database Security
- Gunakan parameterized queries
- Limit database connections
- Regular backup procedures

## 📚 Resources

### Useful Links
- [aiogram Documentation](https://docs.aiogram.dev/)
- [Zoom API Docs](https://developers.zoom.us/docs/api/)
- [Python AsyncIO](https://docs.python.org/3/library/asyncio.html)

### Development Tools
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking
- **pytest**: Testing framework

## 🤝 Contributing

1. Fork repository
2. Create feature branch
3. Make changes dengan tests
4. Ensure all tests pass
5. Submit pull request

### Commit Message Format
```
feat: add new command handler
fix: resolve database connection issue
docs: update installation guide
refactor: improve error handling
test: add unit tests for handlers
```