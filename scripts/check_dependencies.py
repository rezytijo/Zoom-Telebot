import asyncio
import logging
import sys
import subprocess
import json
from datetime import datetime
from bot.logger import get_logger
from config import settings

# Setup logger
logger = get_logger(__name__)

async def check_dependencies():
    """
    Checks for:
    1. Vulnerabilities using pip-audit
    2. Outdated packages using pip list --outdated
    
    Returns a report string if issues found, else None.
    """
    report = []
    
    # 1. Check for Vulnerabilities (pip-audit)
    logger.info("Running dependency vulnerability audit...")
    try:
        # Run pip-audit in JSON mode for easier parsing
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # pip-audit returns non-zero if vulnerabilities found
            try:
                audit_data = json.loads(result.stdout)
                if audit_data:
                    report.append("🚨 <b>SECURITY VULNERABILITIES FOUND:</b>")
                    for item in audit_data:
                        # Depends on pip-audit version, structure might vary. 
                        # Usually list of {package, version, vulns: [{id, aliases, fix_versions}]}
                        pkg = item.get('name', 'unknown')
                        ver = item.get('version', '?')
                        vulns = item.get('vulns', [])
                        
                        vuln_ids = ", ".join([v.get('id') for v in vulns])
                        fix_vers = ", ".join([str(v.get('fix_versions', [])) for v in vulns])
                        
                        report.append(f"- <code>{pkg}</code> ({ver}): {vuln_ids}. Fix: {fix_vers}")
                    report.append("")
            except json.JSONDecodeError:
                # If stdout isn't JSON, maybe it failed strictly
                if result.stderr:
                    logger.error(f"pip-audit failed: {result.stderr}")
                else:
                     logger.warning("pip-audit returned non-zero but valid JSON not found.")

    except FileNotFoundError:
        logger.warning("pip-audit not installed. Skipping vulnerability check.")
    except Exception as e:
        logger.exception(f"Error running pip-audit: {e}")

    # 2. Check for Outdated Packages
    logger.info("Checking for outdated packages...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format", "json"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            outdated = json.loads(result.stdout)
            if outdated:
                report.append("📦 <b>OUTDATED PACKAGES:</b>")
                for item in outdated:
                    pkg = item.get('name')
                    curr = item.get('version')
                    latest = item.get('latest') or "Unknown"
                    report.append(f"- <code>{pkg}</code>: {curr} -> {latest}")
                report.append("")
        else:
            logger.error(f"pip list outdated failed: {result.stderr}")

    except Exception as e:
        logger.exception(f"Error checking outdated packages: {e}")

    if report:
        final_report = "\n".join(report)
        return final_report
    
    return None

if __name__ == "__main__":
    # Test run
    try:
        logging.basicConfig(level=logging.INFO)
        result = asyncio.run(check_dependencies())
        if result:
            print("Issues found:")
            print(result)
        else:
            print("No issues found.")
    except KeyboardInterrupt:
        pass
