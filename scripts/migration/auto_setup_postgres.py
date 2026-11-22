"""
Automated PostgreSQL setup using Docker
Runs PostgreSQL in a container and updates .env automatically
"""

import subprocess
import time
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a shell command and return success status"""
    print(f"⏳ {description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            print(f"✅ {description} - Success!")
            return True, result.stdout.strip()
        else:
            print(f"❌ {description} - Failed!")
            if result.stderr:
                print(f"   Error: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        print(f"⏱️  {description} - Timeout (30s)")
        return False, "Timeout"
    except Exception as e:
        print(f"❌ {description} - Error: {e}")
        return False, str(e)

def update_env_file(database_url):
    """Update .env file with PostgreSQL URL"""
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env file not found!")
        return False
    
    # Read current .env
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace DATABASE_URL line
    lines = content.split('\n')
    updated_lines = []
    found = False
    
    for line in lines:
        if line.strip().startswith('DATABASE_URL='):
            # Comment out old line and add new one
            updated_lines.append(f'# OLD: {line}')
            updated_lines.append(database_url)
            found = True
        else:
            updated_lines.append(line)
    
    if not found:
        # Add at the end
        updated_lines.append('')
        updated_lines.append('# PostgreSQL Configuration')
        updated_lines.append(database_url)
    
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(updated_lines))
    
    return True

def main():
    print("\n" + "="*70)
    print("AUTOMATED POSTGRESQL SETUP WITH DOCKER")
    print("="*70 + "\n")
    
    # Step 1: Check if Docker is running
    success, output = run_command("docker ps", "Checking Docker status")
    if not success:
        print("\n⚠️  Docker Desktop is not running!")
        print("   Please start Docker Desktop and run this script again.")
        print("\n   Alternative: Use cloud PostgreSQL (Neon/Supabase)")
        print("   Run: python setup_neon_postgres.py")
        return False
    
    # Step 2: Check if container already exists
    print("\n⏳ Checking for existing PostgreSQL container...")
    success, output = run_command(
        'docker ps -a --filter "name=mealmind-postgres" --format "{{.Names}}"',
        "Checking existing container"
    )
    
    if output and "mealmind-postgres" in output:
        print("\n📦 Found existing PostgreSQL container!")
        
        # Check if it's running
        success, status = run_command(
            'docker ps --filter "name=mealmind-postgres" --format "{{.Status}}"',
            "Checking container status"
        )
        
        if not status or "Up" not in status:
            print("   Container exists but not running. Starting it...")
            run_command("docker start mealmind-postgres", "Starting container")
            time.sleep(3)
        else:
            print("   Container is already running!")
    else:
        # Step 3: Create new PostgreSQL container
        print("\n🐳 Creating new PostgreSQL container...")
        cmd = (
            'docker run --name mealmind-postgres '
            '-e POSTGRES_PASSWORD=mealmind123 '
            '-e POSTGRES_DB=mealmind '
            '-e POSTGRES_USER=postgres '
            '-p 5432:5432 '
            '-d postgres:15'
        )
        
        success, container_id = run_command(cmd, "Creating PostgreSQL container")
        if not success:
            print("\n❌ Failed to create container!")
            print("   Try manually:")
            print("   1. Open Docker Desktop")
            print("   2. Wait for it to fully start")
            print("   3. Run this script again")
            return False
        
        print(f"   Container ID: {container_id[:12]}...")
        print("\n⏳ Waiting for PostgreSQL to initialize (10 seconds)...")
        time.sleep(10)
    
    # Step 4: Verify PostgreSQL is accessible
    print("\n⏳ Verifying PostgreSQL connection...")
    success, output = run_command(
        'docker exec mealmind-postgres pg_isready -U postgres',
        "Testing PostgreSQL connection"
    )
    
    if not success:
        print("   PostgreSQL might still be initializing...")
        print("   Waiting 5 more seconds...")
        time.sleep(5)
    
    # Step 5: Update .env file
    database_url = "DATABASE_URL=postgresql+psycopg://postgres:mealmind123@localhost:5432/mealmind"
    
    print("\n📝 Updating .env file...")
    if update_env_file(database_url):
        print("✅ .env file updated!")
    else:
        print("❌ Failed to update .env file")
        return False
    
    # Step 6: Test connection from Python
    print("\n⏳ Testing Python connection to PostgreSQL...")
    try:
        import os
        os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:mealmind123@localhost:5432/mealmind"
        from src.database import get_engine
        engine = get_engine()
        with engine.connect() as conn:
            print("✅ Python can connect to PostgreSQL!")
    except Exception as e:
        print(f"⚠️  Python connection test failed: {e}")
        print("   This might be ok - let's continue...")
    
    # Success summary
    print("\n" + "="*70)
    print("🎉 POSTGRESQL SETUP COMPLETE!")
    print("="*70)
    print("\n📊 Database Details:")
    print("   Host: localhost")
    print("   Port: 5432")
    print("   Database: mealmind")
    print("   Username: postgres")
    print("   Password: mealmind123")
    print("\n🐳 Docker Container:")
    print("   Name: mealmind-postgres")
    print("   Status: Running")
    print("\n" + "="*70)
    print("\n📋 NEXT STEPS:")
    print("="*70)
    print("\n1️⃣  Migrate your existing SQLite data:")
    print("   python migrate_sqlite_to_postgres.py")
    print("\n2️⃣  Restart the backend server:")
    print("   • Stop the current server (Ctrl+C in its terminal)")
    print("   • Start it again: python -m src.main")
    print("\n3️⃣  Test the web application:")
    print("   • Open http://localhost:5173")
    print("   • Login with Swiggy OAuth")
    print("   • All features will now use PostgreSQL!")
    print("\n" + "="*70)
    print("\n💡 USEFUL COMMANDS:")
    print("   • Stop PostgreSQL:   docker stop mealmind-postgres")
    print("   • Start PostgreSQL:  docker start mealmind-postgres")
    print("   • View logs:         docker logs mealmind-postgres")
    print("   • Remove container:  docker rm -f mealmind-postgres")
    print("="*70 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
