#!/usr/bin/env python3
"""Minimal smoke check for JobQuest runtime dependencies."""

import sys
import subprocess
from pathlib import Path

# Add repo root to sys.path for imports
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

def check_python():
    """Check Python executable and version."""
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version.split()[0]}")
    return True

def check_imports():
    """Check that core modules can be imported."""
    imports = [
        ("config", "config"),
        ("modules.pipeline", "modules.pipeline"),
        ("modules.llm_client", "modules.llm_client"),
        ("modules.job_scraper", "modules.job_scraper"),
        ("modules.parsers", "modules.parsers"),
    ]
    
    for import_name, display_name in imports:
        try:
            __import__(import_name)
            print(f"✓ {display_name}")
        except ImportError as e:
            print(f"✗ {display_name}: {e}")
            return False
    return True

def check_files():
    """Check that required template/prompt files exist."""
    files = [
        "templates/resume.tex",
        "prompts/jobquest_system_prompt.md",
        "prompts/rodrigo-voice.md",
        "prompts/resume_tailor.md",
        "prompts/ats_check.md",
        "prompts/qa_generator.md",
    ]
    
    all_exist = True
    for file_path in files:
        if Path(file_path).exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} (missing)")
            all_exist = False
    return all_exist

def check_subprocess():
    """Check that CLI commands run without errors."""
    checks = [
        ([sys.executable, "apply.py", "--help"], "apply.py --help"),
        ([sys.executable, "apply.py", "http://example.com", "--dry-run"], "apply.py --dry-run"),
    ]
    
    all_pass = True
    for cmd, description in checks:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                print(f"✓ {description}")
            else:
                print(f"✗ {description} (exit {result.returncode})")
                if result.stdout:
                    print(f"  stdout: {result.stdout[:200]}...")
                if result.stderr:
                    print(f"  stderr: {result.stderr[:200]}...")
                all_pass = False
        except subprocess.TimeoutExpired:
            print(f"✗ {description} (timeout)")
            all_pass = False
        except Exception as e:
            print(f"✗ {description}: {e}")
            all_pass = False
    return all_pass

def main():
    print("=== JobQuest Smoke Check ===\n")
    
    checks = [
        ("Python", check_python),
        ("Imports", check_imports),
        ("Files", check_files),
        ("Subprocess", check_subprocess),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n--- {name} ---")
        try:
            results.append(check_func())
        except Exception as e:
            print(f"✗ Check failed: {e}")
            results.append(False)
    
    print("\n=== Summary ===")
    all_passed = all(results)
    
    if all_passed:
        print("✓ All checks passed")
        sys.exit(0)
    else:
        print("✗ Some checks failed")
        sys.exit(1)

if __name__ == "__main__":
    main()