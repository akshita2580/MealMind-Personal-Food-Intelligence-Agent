#!/usr/bin/env python3
"""
Quick status check - verifies MealMind setup before testing.
Run this before starting manual or automated tests.
"""
import os
import sys
from pathlib import Path

def check_file(path: str, description: str) -> bool:
    """Check if file exists."""
    if Path(path).exists():
        print(f"✅ {description}: {path}")
        return True
    else:
        print(f"❌ {description} NOT FOUND: {path}")
        return False

def check_env_var(var: str, description: str) -> bool:
    """Check if environment variable is set."""
    value = os.getenv(var)
    if value:
        masked = value[:10] + "..." if len(value) > 10 else value
        print(f"✅ {description}: {masked}")
        return True
    else:
        print(f"⚠️  {description} NOT SET: {var}")
        return False

def check_database() -> bool:
    """Check database and count records."""
    try:
        from src.database import get_session
        from src.models import User, Order, SwiggyConnection
        from sqlmodel import select
        
        with get_session() as db:
            users = db.exec(select(User)).all()
            orders = db.exec(select(Order)).all()
            connections = db.exec(select(SwiggyConnection)).all()
            
            print(f"\n📊 Database Status:")
            print(f"   Users: {len(users)}")
            print(f"   Orders: {len(orders)}")
            print(f"   Connections: {len(connections)}")
            
            if len(users) > 0 and len(connections) > 0:
                print(f"✅ Database has data")
                return True
            else:
                print(f"⚠️  Database has no users or connections")
                return False
    except Exception as e:
        print(f"❌ Database check failed: {str(e)}")
        return False

def check_processes() -> tuple[bool, bool]:
    """Check if backend and frontend are running."""
    import socket
    
    backend_running = False
    frontend_running = False
    
    # Check backend (port 8000)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8000))
        sock.close()
        backend_running = result == 0
    except:
        pass
    
    # Check frontend (port 5173)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 5173))
        sock.close()
        frontend_running = result == 0
    except:
        pass
    
    if backend_running:
        print(f"✅ Backend running on http://127.0.0.1:8000")
    else:
        print(f"❌ Backend NOT running on port 8000")
        print(f"   Start with: python -m src.main")
    
    if frontend_running:
        print(f"✅ Frontend running on http://localhost:5173")
    else:
        print(f"❌ Frontend NOT running on port 5173")
        print(f"   Start with: cd frontend && npm run dev")
    
    return backend_running, frontend_running

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                   MealMind Web - Quick Status Check                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")
    
    checks = []
    
    # Check critical files
    print("\n📁 File Structure:")
    checks.append(check_file("src/main.py", "Backend entry point"))
    checks.append(check_file("src/api_web.py", "Web API endpoints"))
    checks.append(check_file("frontend/package.json", "Frontend config"))
    checks.append(check_file("frontend/src/App.tsx", "React app"))
    checks.append(check_file("data/swiggy.db", "Database"))
    
    # Check environment
    print("\n🔐 Environment Variables:")
    checks.append(check_env_var("SWIGGY_CLIENT_ID", "Swiggy Client ID"))
    check_env_var("SWIGGY_CLIENT_SECRET", "Swiggy Client Secret")  # Optional
    checks.append(check_env_var("ENCRYPTION_KEY", "Encryption Key"))
    
    # Check database
    print()
    checks.append(check_database())
    
    # Check running processes
    print("\n🚀 Running Processes:")
    backend_running, frontend_running = check_processes()
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    passed = sum(1 for c in checks if c)
    total = len(checks)
    
    print(f"System Checks: {passed}/{total} passed")
    
    if backend_running and frontend_running:
        print("✅ Application is READY for testing!")
        print("\nNext steps:")
        print("1. Open browser: http://localhost:5173")
        print("2. Login with Swiggy OAuth")
        print("3. Run: python test_all_endpoints.py")
        print("4. Follow: TESTING_INSTRUCTIONS.md")
        return 0
    elif backend_running:
        print("⚠️  Backend running, but frontend NOT running")
        print("\nStart frontend:")
        print("  cd frontend && npm run dev")
        return 1
    elif frontend_running:
        print("⚠️  Frontend running, but backend NOT running")
        print("\nStart backend:")
        print("  python -m src.main")
        return 1
    else:
        print("❌ Application NOT running")
        print("\nStart both services:")
        print("  Terminal 1: python -m src.main")
        print("  Terminal 2: cd frontend && npm run dev")
        return 1

if __name__ == "__main__":
    sys.exit(main())
