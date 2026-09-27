#!/usr/bin/env python3
"""
Shortener Configuration Migration Script

Script untuk melakukan migrasi shorteners.json ke versi terbaru.
Fitur:
- Deteksi otomatis jika migrasi diperlukan
- Backup file lama sebelum migrasi
- Preservasi semua kustomisasi pengguna
- Preview perubahan sebelum commit

Usage:
    python scripts/migrate_shorteners.py              # Jalankan migrasi jika diperlukan
    python scripts/migrate_shorteners.py --force      # Paksa migrasi meskipun sudah versi terbaru
    python scripts/migrate_shorteners.py --help       # Tampilkan bantuan
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from shortener import migrate_shortener_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_banner():
    """Print welcome banner"""
    print("\n" + "="*70)
    print("  🔄 Shortener Configuration Migration Tool")
    print("="*70 + "\n")


def check_config_file():
    """Check if shorteners.json exists"""
    config_file = os.path.join(settings.DATA_DIR, "shorteners.json")
    
    if not os.path.exists(config_file):
        logger.error(f"❌ Config file not found: {config_file}")
        return None
    
    return config_file


def preview_changes(config_file: str):
    """Show preview of what will change"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        current_version = config.get('version', '1.0')
        provider_count = len(config.get('providers', {}))
        
        print(f"  📋 Current Config Information:")
        print(f"     • Version: {current_version}")
        print(f"     • Providers: {provider_count}")
        print(f"     • File: {config_file}")
        print()
        
        print(f"  🎯 Migration Target:")
        print(f"     • New Version: 2.0")
        print(f"     • What will happen:")
        print(f"       - Config structure updated to latest schema")
        print(f"       - All provider configurations will be preserved")
        print(f"       - Custom providers will be kept as-is")
        print(f"       - Backup created: {config_file}.pre-migration-backup")
        print()
        
    except Exception as e:
        logger.error(f"Error reading config: {e}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Migrate shorteners.json to latest schema version',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/migrate_shorteners.py                # Auto-detect dan migrasi jika perlu
  python scripts/migrate_shorteners.py --force        # Paksa migrasi
  python scripts/migrate_shorteners.py --preview      # Preview saja, tidak migrasi
        """
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force migration even if config is already at latest version'
    )
    
    parser.add_argument(
        '--preview',
        action='store_true',
        help='Show preview only, do not perform migration'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print_banner()
    
    # Check config file exists
    config_file = check_config_file()
    if not config_file:
        print("❌ Migration failed: Config file not found\n")
        return 1
    
    # Show preview
    preview_changes(config_file)
    
    if args.preview:
        print("  ℹ️  Preview mode - No changes will be made\n")
        return 0
    
    # Perform migration
    try:
        if args.force:
            logger.info("Force migration mode enabled")
        
        print("  ⏳ Starting migration...\n")
        
        # Import here to ensure config is loaded
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        # Force migration if requested
        if args.force:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            from shortener import DynamicShortener
            shortener = DynamicShortener(config_file)
            shortener._migrate_config(config)
            
            print("✅ Migration completed successfully!")
            print(f"   • Backup saved to: {config_file}.pre-migration-backup")
            print(f"   • Config updated at: {config_file}\n")
        else:
            # Auto-detect and migrate
            migrated = migrate_shortener_config()
            
            if migrated:
                print("✅ Migration completed successfully!")
                print(f"   • Backup saved to: {config_file}.pre-migration-backup")
                print(f"   • Config updated at: {config_file}\n")
                return 0
            else:
                print("ℹ️  No migration needed - Config is already at latest version\n")
                return 0
        
        return 0
        
    except Exception as e:
        logger.exception("Migration failed")
        print(f"\n❌ Migration failed: {e}\n")
        return 1


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
