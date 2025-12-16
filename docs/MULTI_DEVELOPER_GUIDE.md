# Multi-Developer Quick Reference

**Keep this as a quick checklist for your team!**

---

## 🚀 Before You Start

```bash
# 1. Setup
git checkout Development-WithAPP
git pull origin Development-WithAPP
git checkout -b feature/your-feature-name

# 2. Install & prepare
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python dev.py setup

# 3. Work on YOUR module only
# Dev 1: bot/
# Dev 2: zoom/
# Dev 3: db/
# Dev 4: c2/
# Dev 5: shortener/
```

---

## 📁 Your Module (Example: Bot Developer)

```
bot/
├── __init__.py        # Don't touch
├── main.py            # Setup - only edit initialization
├── handlers.py        # ✅ EDIT HERE - Your commands
├── keyboards.py       # ✅ EDIT HERE - Your UI buttons
├── auth.py            # ✅ EDIT HERE - Auth logic
└── middleware.py      # ✅ EDIT HERE - Middleware
```

**You ONLY edit:**
- `handlers.py` - Add new `/commands`
- `keyboards.py` - Add new buttons/keyboards
- `auth.py` - Authentication logic
- `middleware.py` - Request/response processing

**DO NOT edit:**
- `main.py` - (Unless you know what you're doing)
- Other modules' files (zoom/, db/, c2/)

---

## 🔗 Using Other Modules

### **Calling zoom/ from bot/**

```python
# bot/handlers.py
from zoom import zoom_client

@router.message(Command("create_meeting"))
async def handle_create_meeting(message: Message):
    result = await zoom_client.create_meeting(
        topic="Team Meeting",
        date="2025-12-20",
        time="14:00",
        settings={"auto_recording": "local"}
    )
    # Result has meeting_id, join_url, etc
```

### **Calling db/ from bot/**

```python
# bot/handlers.py
from db import add_meeting, list_meetings

@router.message(Command("list"))
async def handle_list_meetings(message: Message):
    meetings = await list_meetings()
    # meetings is a list of meeting records
```

### **Using config/ from anywhere**

```python
# Any module
from config import settings

if settings.C2_ENABLED:
    # Show agent control buttons
else:
    # Hide agent control buttons
```

---

## 📝 Committing Your Changes

```bash
# See what you changed
git status

# Stage your changes
git add .

# Commit with clear message
git commit -m "feat(bot): Add /status command to show meeting list"
git commit -m "fix(zoom): Handle API timeout gracefully"
git commit -m "refactor(db): Optimize get_meetings query"

# Push to your branch
git push origin feature/your-feature-name

# Create Pull Request on GitHub/GitLab to Development-WithAPP
```

**Commit message format:** `type(module): description`
- `feat:` - New feature
- `fix:` - Bug fix
- `refactor:` - Code reorganization
- `docs:` - Documentation
- `style:` - Code style
- `test:` - Tests

---

## 🧪 Testing Before Commit

```bash
# Test imports work
python dev.py test

# Check configuration is valid
python dev.py check

# Run the bot locally
python dev.py run --watch

# Test your specific changes manually
# Open Telegram, test the command you added
```

---

## ⚠️ DO's and DON'Ts

### DO ✅
- Work on YOUR assigned module only
- Create feature branch from `Development-WithAPP`
- Write clear commit messages
- Test locally before pushing
- Use `python dev.py run --watch` (auto-restart)
- Notify lead if you need to change interfaces

### DON'T ❌
- Don't commit to `main` branch
- Don't edit other developers' modules
- Don't hardcode configuration (use `settings`)
- Don't change function signatures without discussion
- Don't push directly to `Development-WithAPP`
- Don't merge your own Pull Requests

---

## 🆘 Common Issues

### **Merge Conflict**
```bash
# Update your branch
git fetch origin
git rebase origin/Development-WithAPP

# If conflict, resolve manually, then:
git add .
git rebase --continue
```

### **Accidentally edited wrong file**
```bash
# Discard changes to that file
git checkout -- path/to/file.py

# Or start over
git reset --hard origin/feature/your-feature-name
```

### **Need to pull latest changes**
```bash
# Update from Development-WithAPP
git fetch origin
git rebase origin/Development-WithAPP

# Continue working
```

### **Bot won't start after changes**
```bash
# Check configuration
python dev.py check

# Check imports
python dev.py test

# Check logs for errors
tail -f logs/
```

---

## 📞 Need Help?

1. **Module question?** → Check the module's docstrings
2. **Interface question?** → Check function signatures
3. **Merge conflict?** → Contact the lead
4. **Architecture question?** → Read `docs/ARCHITECTURE.md`
5. **Configuration question?** → Check `.env.example`

---

## 🎯 Your Workflow Today

```
1. git checkout -b feature/your-feature ✅
2. python dev.py setup ✅
3. Make your changes to bot/handlers.py ✅
4. python dev.py test ✅
5. git commit -m "feat(bot): description" ✅
6. git push origin feature/your-feature ✅
7. Create Pull Request ✅
8. Wait for review & merge ✅
```

**Keep it simple, keep it focused, keep it documented!** 🚀
