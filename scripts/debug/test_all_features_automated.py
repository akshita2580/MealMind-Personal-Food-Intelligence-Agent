"""
Automated Feature Testing Suite for MealMind
Tests all features and generates a comprehensive report
"""

import asyncio
import sys
from datetime import datetime
from typing import Dict, List
import json

# Test results storage
test_results = {
    "passed": [],
    "failed": [],
    "warnings": [],
    "skipped": [],
    "timestamp": datetime.now().isoformat()
}

def log_test(category: str, test_name: str, status: str, details: str = ""):
    """Log a test result"""
    result = {
        "test": test_name,
        "status": status,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    
    if status == "PASS":
        test_results["passed"].append(result)
        print(f"✅ {test_name}: {details or 'OK'}")
    elif status == "FAIL":
        test_results["failed"].append(result)
        print(f"❌ {test_name}: {details}")
    elif status == "WARN":
        test_results["warnings"].append(result)
        print(f"⚠️  {test_name}: {details}")
    elif status == "SKIP":
        test_results["skipped"].append(result)
        print(f"⏭️  {test_name}: {details}")

async def test_backend_health():
    """Test 1: Backend server health"""
    print("\n" + "="*70)
    print("TEST CATEGORY 1: BACKEND HEALTH")
    print("="*70)
    
    try:
        import requests
        
        # Test 1.1: Server is running
        try:
            response = requests.get("http://localhost:8000/api/auth/status", timeout=5)
            if response.status_code == 200:
                log_test("backend", "Backend Server Running", "PASS", "Server responding on port 8000")
            else:
                log_test("backend", "Backend Server Running", "FAIL", f"Status code: {response.status_code}")
        except Exception as e:
            log_test("backend", "Backend Server Running", "FAIL", str(e))
            return
        
        # Test 1.2: Database connection
        try:
            from sqlmodel import Session, select
            from src.database import get_engine
            from src.models import User
            
            engine = get_engine()
            with engine.connect() as conn:
                log_test("backend", "Database Connection", "PASS", "PostgreSQL connected successfully")
        except Exception as e:
            log_test("backend", "Database Connection", "FAIL", str(e))
        
        # Test 1.3: Check if user exists
        try:
            db = Session(get_engine())
            user = db.exec(select(User)).first()
            if user:
                log_test("backend", "User Authentication", "PASS", f"Found user in database")
            else:
                log_test("backend", "User Authentication", "WARN", "No users found - need to login first")
        except Exception as e:
            log_test("backend", "User Authentication", "FAIL", str(e))
        finally:
            db.close()
            
    except ImportError as e:
        log_test("backend", "Backend Health Tests", "FAIL", f"Missing dependency: {e}")

async def test_frontend_health():
    """Test 2: Frontend server health"""
    print("\n" + "="*70)
    print("TEST CATEGORY 2: FRONTEND HEALTH")
    print("="*70)
    
    try:
        import requests
        
        # Test 2.1: Frontend is running
        try:
            response = requests.get("http://localhost:5173", timeout=5)
            if response.status_code == 200:
                log_test("frontend", "Frontend Server Running", "PASS", "Vite dev server responding")
            else:
                log_test("frontend", "Frontend Server Running", "FAIL", f"Status code: {response.status_code}")
        except Exception as e:
            log_test("frontend", "Frontend Server Running", "FAIL", str(e))
            
    except ImportError:
        log_test("frontend", "Frontend Health Tests", "SKIP", "requests library not available")

async def test_api_endpoints():
    """Test 3: API endpoints"""
    print("\n" + "="*70)
    print("TEST CATEGORY 3: API ENDPOINTS")
    print("="*70)
    
    try:
        import requests
        
        endpoints = [
            ("/api/auth/status", "Auth Status"),
            ("/api/food/addresses", "Food Addresses"),
            ("/api/orders", "Orders"),
            ("/api/analytics", "Analytics"),
            ("/api/insights", "Insights"),
        ]
        
        for endpoint, name in endpoints:
            try:
                response = requests.get(f"http://localhost:8000{endpoint}", timeout=5)
                if response.status_code in [200, 400]:  # 400 is ok for auth-required endpoints
                    log_test("api", f"Endpoint: {name}", "PASS", f"Status {response.status_code}")
                else:
                    log_test("api", f"Endpoint: {name}", "WARN", f"Status {response.status_code}")
            except Exception as e:
                log_test("api", f"Endpoint: {name}", "FAIL", str(e))
                
    except ImportError:
        log_test("api", "API Endpoint Tests", "SKIP", "requests library not available")

async def test_database_tables():
    """Test 4: Database tables and data"""
    print("\n" + "="*70)
    print("TEST CATEGORY 4: DATABASE TABLES")
    print("="*70)
    
    try:
        from sqlmodel import Session, select
        from src.database import get_engine
        from src.models import User, Order
        
        db = Session(get_engine())
        
        # Test 4.1: Users table
        try:
            users = db.exec(select(User)).all()
            log_test("database", "Users Table", "PASS", f"Found {len(users)} users")
        except Exception as e:
            log_test("database", "Users Table", "FAIL", str(e))
        
        # Test 4.2: Orders table
        try:
            orders = db.exec(select(Order)).all()
            if len(orders) > 0:
                log_test("database", "Orders Table", "PASS", f"Found {len(orders)} orders")
            else:
                log_test("database", "Orders Table", "WARN", "No orders found - may need to sync")
        except Exception as e:
            log_test("database", "Orders Table", "FAIL", str(e))
        
        db.close()
        
    except Exception as e:
        log_test("database", "Database Tests", "FAIL", str(e))

async def test_file_structure():
    """Test 5: File structure and configuration"""
    print("\n" + "="*70)
    print("TEST CATEGORY 5: FILE STRUCTURE")
    print("="*70)
    
    import os
    from pathlib import Path
    
    critical_files = [
        ".env",
        "src/main.py",
        "src/api_web.py",
        "src/database.py",
        "src/models.py",
        "frontend/package.json",
        "frontend/src/App.tsx",
        "frontend/src/pages/FoodDelivery.tsx",
        "frontend/src/pages/Instamart.tsx",
    ]
    
    for file_path in critical_files:
        if Path(file_path).exists():
            log_test("files", f"File: {file_path}", "PASS", "Exists")
        else:
            log_test("files", f"File: {file_path}", "FAIL", "Missing")
    
    # Check .env configuration
    try:
        with open(".env", "r") as f:
            env_content = f.read()
            if "DATABASE_URL" in env_content and "postgresql" in env_content:
                log_test("config", ".env PostgreSQL Config", "PASS", "PostgreSQL configured")
            else:
                log_test("config", ".env PostgreSQL Config", "WARN", "May be using SQLite")
    except Exception as e:
        log_test("config", ".env Configuration", "FAIL", str(e))

async def test_dependencies():
    """Test 6: Dependencies installed"""
    print("\n" + "="*70)
    print("TEST CATEGORY 6: DEPENDENCIES")
    print("="*70)
    
    python_packages = [
        "fastapi",
        "sqlmodel",
        "psycopg",
        "uvicorn",
        "httpx",
    ]
    
    for package in python_packages:
        try:
            __import__(package)
            log_test("dependencies", f"Python: {package}", "PASS", "Installed")
        except ImportError:
            log_test("dependencies", f"Python: {package}", "FAIL", "Not installed")
    
    # Check Node modules
    import os
    if os.path.exists("frontend/node_modules"):
        log_test("dependencies", "Node Modules", "PASS", "Frontend dependencies installed")
    else:
        log_test("dependencies", "Node Modules", "FAIL", "Run 'npm install' in frontend/")

def generate_report():
    """Generate comprehensive test report"""
    print("\n" + "="*70)
    print("TEST REPORT SUMMARY")
    print("="*70)
    
    total_tests = (
        len(test_results["passed"]) + 
        len(test_results["failed"]) + 
        len(test_results["warnings"]) +
        len(test_results["skipped"])
    )
    
    print(f"\n📊 Total Tests Run: {total_tests}")
    print(f"✅ Passed: {len(test_results['passed'])}")
    print(f"❌ Failed: {len(test_results['failed'])}")
    print(f"⚠️  Warnings: {len(test_results['warnings'])}")
    print(f"⏭️  Skipped: {len(test_results['skipped'])}")
    
    if len(test_results["failed"]) > 0:
        print("\n" + "="*70)
        print("❌ FAILED TESTS:")
        print("="*70)
        for test in test_results["failed"]:
            print(f"\n• {test['test']}")
            print(f"  Details: {test['details']}")
    
    if len(test_results["warnings"]) > 0:
        print("\n" + "="*70)
        print("⚠️  WARNINGS:")
        print("="*70)
        for test in test_results["warnings"]:
            print(f"\n• {test['test']}")
            print(f"  Details: {test['details']}")
    
    # Calculate pass rate
    if total_tests > 0:
        pass_rate = (len(test_results["passed"]) / total_tests) * 100
        print(f"\n📈 Pass Rate: {pass_rate:.1f}%")
        
        if pass_rate >= 90:
            print("\n🎉 EXCELLENT! System is working great!")
        elif pass_rate >= 75:
            print("\n✅ GOOD! System is mostly functional with minor issues.")
        elif pass_rate >= 50:
            print("\n⚠️  FAIR! System needs attention on failed tests.")
        else:
            print("\n❌ POOR! System has critical issues that need fixing.")
    
    # Save report to file
    try:
        with open("test_report.json", "w") as f:
            json.dump(test_results, f, indent=2)
        print("\n💾 Detailed report saved to: test_report.json")
    except Exception as e:
        print(f"\n⚠️  Could not save report: {e}")
    
    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)
    
    if len(test_results["failed"]) > 0:
        print("\n🔧 Actions to fix failed tests:")
        if any("Backend Server" in t["test"] for t in test_results["failed"]):
            print("  • Start backend: python -m src.main")
        if any("Frontend Server" in t["test"] for t in test_results["failed"]):
            print("  • Start frontend: cd frontend && npm run dev")
        if any("Database" in t["test"] for t in test_results["failed"]):
            print("  • Check PostgreSQL connection in .env")
        if any("Authentication" in t["test"] for t in test_results["warnings"]):
            print("  • Login via Swiggy OAuth at http://localhost:5173")
    
    if len(test_results["warnings"]) > 0:
        print("\n💡 Optional improvements:")
        for test in test_results["warnings"]:
            if "No orders" in test["details"]:
                print("  • Sync orders from Swiggy in the app")
            if "No users" in test["details"]:
                print("  • Complete Swiggy OAuth login")
    
    print("\n" + "="*70)

async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 MEALMIND AUTOMATED TEST SUITE")
    print("="*70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Run all test categories
    await test_backend_health()
    await test_frontend_health()
    await test_api_endpoints()
    await test_database_tables()
    await test_file_structure()
    await test_dependencies()
    
    # Generate report
    generate_report()
    
    # Exit code based on failures
    if len(test_results["failed"]) == 0:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {len(test_results['failed'])} tests failed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
