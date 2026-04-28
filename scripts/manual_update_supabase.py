#!/usr/bin/env python3
"""
Manual script to scrape, build catalog, and upload to Supabase.
Use this when you don't have a VM running automation.

Usage:
    python scripts/manual_update_supabase.py --stores exito carulla olimpica
    python scripts/manual_update_supabase.py --stores all
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def run_command(cmd, description):
    """Run a command and print status."""
    print(f"\n{'='*60}")
    print(f"▶ {description}")
    print(f"{'='*60}")
    env = os.environ.copy()
    env["HEADLESS"] = "true"
    result = subprocess.run(cmd, shell=True, env=env)
    if result.returncode != 0:
        print(f"❌ Failed: {description}")
        return False
    print(f"✅ Success: {description}")
    return True

def main():
    parser = argparse.ArgumentParser(
        description="Manually update LicorScan Supabase catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/manual_update_supabase.py --stores exito
  python scripts/manual_update_supabase.py --stores carulla olimpica
  python scripts/manual_update_supabase.py --stores all
        """
    )
    parser.add_argument(
        "--stores",
        nargs="+",
        default=["exito", "carulla", "olimpica"],
        help="Stores to scrape (default: exito carulla olimpica). Use 'all' for all stores.",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping; only rebuild catalog and upload",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip Supabase upload; only scrape and build catalog",
    )
    
    args = parser.parse_args()
    
    stores = args.stores
    if "all" in stores:
        stores = ["exito", "carulla", "olimpica", "d1"]
    
    project_root = Path(__file__).parent.parent
    
    # Step 1: Scrape stores
    if not args.skip_scrape:
        for store in stores:
            cmd = f"cd {project_root} && py -3 -m scraper.main --store {store} --verbose"
            if not run_command(cmd, f"Scraping {store}"):
                print(f"Warning: {store} scraping failed, continuing...")
    
    # Step 2: Build catalog
    cmd = f"cd {project_root} && py -3 build_front_catalog.py"
    if not run_command(cmd, "Building frontend catalog"):
        print("❌ Catalog build failed. Aborting.")
        return False
    
    # Step 3: Upload to Supabase
    if not args.skip_upload:
        cmd = f"cd {project_root} && py -3 scripts/upload_to_supabase.py"
        if not run_command(cmd, "Uploading to Supabase"):
            print("❌ Supabase upload failed. Aborting.")
            return False
    
    # Step 4: Verify data in Supabase
    print(f"\n{'='*60}")
    print("✅ Catalog update complete!")
    print(f"{'='*60}")
    print("\nNext steps:")
    print("1. Verify data at: https://app.supabase.com/project/.../editor/")
    print("2. Frontend will auto-fetch latest data from Supabase")
    print("3. To deploy: git add -A && git commit -m 'Auto: Update catalog'")
    print("4. Push to GitHub: git push origin main")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
