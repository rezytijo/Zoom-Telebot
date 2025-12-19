#!/usr/bin/env python3
"""
Demo Script - Shortener Config Migration Feature

Script ini mendemonstrasikan bagaimana fitur migrasi bekerja.
Menunjukkan:
1. Deteksi config version
2. Preservasi data
3. Backup creation
4. Migration process
"""

import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from shortener import DynamicShortener, migrate_shortener_config


def print_header(text):
    """Print formatted header"""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70 + "\n")


def print_section(text):
    """Print formatted section"""
    print(f"\n📌 {text}\n")


def demo_config_structure():
    """Demo 1: Show current config structure"""
    print_header("DEMO 1: Current Config Structure")
    
    config_file = os.path.join(settings.DATA_DIR, "shorteners.json")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print_section("Config Metadata")
        print(f"  Version        : {config.get('version', 'N/A')}")
        print(f"  Default        : {config.get('default_provider', 'N/A')}")
        print(f"  Fallback       : {config.get('fallback_provider', 'N/A')}")
        
        print_section("Providers Configured")
        providers = config.get('providers', {})
        for name, provider in providers.items():
            enabled = "✅ ENABLED" if provider.get('enabled') else "❌ DISABLED"
            auth_type = provider.get('auth', {}).get('type', 'none')
            print(f"  • {name:20} {enabled:15} (auth: {auth_type})")
        
        print_section("Sample Provider Structure (tinyurl)")
        if 'tinyurl' in providers:
            tinyurl = providers['tinyurl']
            print(f"  Name        : {tinyurl.get('name')}")
            print(f"  Description : {tinyurl.get('description')}")
            print(f"  API URL     : {tinyurl.get('api_url')}")
            print(f"  Method      : {tinyurl.get('method')}")
            print(f"  Response    : {tinyurl.get('response_type')}")
            print(f"  Auth Type   : {tinyurl.get('auth', {}).get('type')}")
        
    except Exception as e:
        print(f"❌ Error reading config: {e}")


def demo_migration_detection():
    """Demo 2: Show migration detection logic"""
    print_header("DEMO 2: Migration Detection Logic")
    
    config_file = os.path.join(settings.DATA_DIR, "shorteners.json")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        shortener = DynamicShortener(config_file)
        config_version = config.get('version', '1.0')
        
        print_section("Checking Migration Needs")
        print(f"  Current Version   : v{config_version}")
        print(f"  Target Version    : v2.0")
        
        needs_migration = shortener._needs_migration(config_version, config)
        
        print_section("Detection Results")
        if needs_migration:
            print(f"  ✅ Migration NEEDED")
            print(f"     - Version mismatch or missing fields detected")
        else:
            print(f"  ✅ Migration NOT NEEDED")
            print(f"     - Config is already at latest version")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def demo_preservatiom_logic():
    """Demo 3: Show what data is preserved"""
    print_header("DEMO 3: Data Preservation During Migration")
    
    print_section("What Gets Preserved")
    preserved_items = [
        "✅ Provider enabled/disabled status",
        "✅ API keys and authentication tokens",
        "✅ Custom headers configuration",
        "✅ Body parameters and formatting",
        "✅ Custom providers (user-defined)",
        "✅ API URLs (if customized)",
        "✅ HTTP methods",
        "✅ Any other custom fields"
    ]
    
    for item in preserved_items:
        print(f"  {item}")
    
    print_section("What Gets Updated")
    updated_items = [
        "📝 Version field (to 2.0)",
        "📝 Schema structure (to latest)",
        "📝 New fields (if any)",
        "📝 Metadata (migration source version)"
    ]
    
    for item in updated_items:
        print(f"  {item}")


def demo_migration_process():
    """Demo 4: Show migration process"""
    print_header("DEMO 4: Migration Process Explanation")
    
    print_section("Step-by-Step Migration Flow")
    
    steps = [
        ("1", "Load old configuration", "Read shorteners.json from disk"),
        ("2", "Check version", "Compare with target version (2.0)"),
        ("3", "Detect migration need", "Analyze structure and fields"),
        ("4", "Create backup", "Save pre-migration copy: .pre-migration-backup"),
        ("5", "Get default template", "Load new schema structure"),
        ("6", "Merge configurations", "Preserve old + merge with new"),
        ("7", "Preserv user data", "Keep all customizations intact"),
        ("8", "Save updated config", "Write migrated config to disk"),
        ("9", "Update version", "Set version to 2.0"),
        ("10", "Reload providers", "Load into memory for use")
    ]
    
    for num, title, description in steps:
        print(f"  [{num:2}] {title:30} → {description}")


def demo_backup_files():
    """Demo 5: Show backup files"""
    print_header("DEMO 5: Backup Files Management")
    
    data_dir = settings.DATA_DIR
    config_file = os.path.join(data_dir, "shorteners.json")
    backup_file = config_file + ".pre-migration-backup"
    
    print_section("Files in data/ directory")
    
    try:
        # Check main file
        if os.path.exists(config_file):
            size = os.path.getsize(config_file)
            print(f"  ✅ {os.path.basename(config_file):40} ({size} bytes)")
        
        # Check backup file
        if os.path.exists(backup_file):
            size = os.path.getsize(backup_file)
            print(f"  ✅ {os.path.basename(backup_file):40} ({size} bytes)")
        else:
            print(f"  ⚪ {os.path.basename(backup_file):40} (not yet created)")
        
        # Check old backup
        old_backup = config_file + ".back"
        if os.path.exists(old_backup):
            size = os.path.getsize(old_backup)
            print(f"  ⚪ {os.path.basename(old_backup):40} ({size} bytes)")
    
    except Exception as e:
        print(f"  ❌ Error listing files: {e}")
    
    print_section("Rollback Procedure")
    print(f"  If migration goes wrong, you can restore:")
    print(f"    cp {os.path.basename(backup_file)} {os.path.basename(config_file)}")


def demo_api_usage():
    """Demo 6: Show API usage examples"""
    print_header("DEMO 6: API Usage Examples")
    
    print_section("Example 1: Auto-detect and migrate")
    print("""
    from shortener import migrate_shortener_config
    
    result = migrate_shortener_config()
    if result:
        print("✅ Migration completed")
    else:
        print("ℹ️ No migration needed")
    """)
    
    print_section("Example 2: Direct class usage")
    print("""
    from shortener import DynamicShortener
    
    shortener = DynamicShortener()
    
    # Check if needed
    if shortener._needs_migration(version, config):
        # Do migration
        migrated = shortener._migrate_config(old_config)
    """)
    
    print_section("Example 3: Command-line")
    print("""
    # Preview changes
    python scripts/migrate_shorteners.py --preview
    
    # Run migration
    python scripts/migrate_shorteners.py
    
    # Force migration
    python scripts/migrate_shorteners.py --force
    """)


def demo_safety_features():
    """Demo 7: Show safety features"""
    print_header("DEMO 7: Safety Features")
    
    safety_features = {
        "🔒 Backup": "Auto backup created before migration",
        "📝 Logging": "Detailed logging of all actions",
        "⏮️  Rollback": "Easy rollback from backup anytime",
        "🛡️ Validation": "Config validated before and after",
        "⚛️ Atomic": "Migration is all-or-nothing",
        "💾 Preservation": "100% user customization preserved",
        "🔄 Reversible": "Can undo migration if needed",
        "🐛 Error Handling": "Proper exception handling"
    }
    
    for feature, description in safety_features.items():
        print(f"  {feature:20} : {description}")


def main():
    """Run all demos"""
    print("\n" + "="*70)
    print("  🎯 SHORTENER CONFIG MIGRATION FEATURE - DEMO")
    print("="*70)
    
    demos = [
        ("1", "Config Structure", demo_config_structure),
        ("2", "Migration Detection", demo_migration_detection),
        ("3", "Data Preservation", demo_preservatiom_logic),
        ("4", "Migration Process", demo_migration_process),
        ("5", "Backup Management", demo_backup_files),
        ("6", "API Usage", demo_api_usage),
        ("7", "Safety Features", demo_safety_features)
    ]
    
    print("\n📚 Available Demos:\n")
    for num, name, _ in demos:
        print(f"  [{num}] {name}")
    
    print(f"  [0] Run All Demos")
    print(f"  [q] Quit\n")
    
    choice = input("Select demo (0-7, q to quit): ").strip().lower()
    
    if choice == 'q':
        print("\n👋 Goodbye!\n")
        return 0
    
    if choice == '0':
        # Run all demos
        for num, name, demo_func in demos:
            demo_func()
            input(f"\nPress Enter to continue to next demo...")
    else:
        # Run selected demo
        try:
            idx = int(choice)
            if 1 <= idx <= len(demos):
                demos[idx-1][2]()
            else:
                print(f"❌ Invalid choice: {choice}")
                return 1
        except ValueError:
            print(f"❌ Invalid input: {choice}")
            return 1
    
    print("\n" + "="*70)
    print("  ✅ DEMO COMPLETE")
    print("="*70 + "\n")
    
    print("📚 For more information, see:")
    print("   - docs/SHORTENER_MIGRATION.md")
    print("   - MIGRATION_FEATURE_README.md")
    print("   - FITUR_MIGRASI_SUMMARY.md\n")
    
    return 0


if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)
