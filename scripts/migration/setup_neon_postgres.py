"""
Interactive PostgreSQL setup using Neon (free cloud PostgreSQL)
This script helps you set up a cloud PostgreSQL database in minutes
"""

import os
import sys
from pathlib import Path

def update_env_file(database_url):
    """Update .env file with PostgreSQL URL"""
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ .env file not found!")
        return False
    
    # Read current .env
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Update DATABASE_URL line
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith('DATABASE_URL='):
            # Keep old value as comment
            old_value = line.strip()
            lines[i] = f'# OLD: {old_value}\n{database_url}\n'
            updated = True
            break
    
    if not updated:
        # Add if not found
        lines.append(f'\n# PostgreSQL Configuration\n{database_url}\n')
    
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    return True

def main():
    print("\n" + "="*70)
    print("POSTGRESQL SETUP FOR MEALMIND")
    print("="*70 + "\n")
    
    print("I'll help you set up a FREE cloud PostgreSQL database.\n")
    print("Options:")
    print("1. Neon (recommended - free, fast, no credit card)")
    print("2. Supabase (free tier)")
    print("3. Manual entry (if you already have a PostgreSQL URL)")
    print("4. Local Docker (requires Docker Desktop running)")
    
    choice = input("\nChoose an option (1-4): ").strip()
    
    if choice == "1":
        print("\n📝 NEON SETUP INSTRUCTIONS:\n")
        print("1. Open your browser and go to: https://neon.tech")
        print("2. Click 'Sign Up' (use GitHub, Google, or email)")
        print("3. Create a new project named 'MealMind'")
        print("4. After creation, you'll see a connection string")
        print("5. Copy the ENTIRE connection string")
        print("   (should look like: postgresql://user:pass@ep-xxx.region.aws.neon.tech/neondb)")
        print("\n" + "-"*70)
        
        conn_string = input("\nPaste your Neon connection string here: ").strip()
        
        if not conn_string.startswith("postgresql://"):
            print("❌ Invalid connection string. Must start with 'postgresql://'")
            return False
        
        # Add psycopg driver
        conn_string = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
        database_url = f"DATABASE_URL={conn_string}"
        
    elif choice == "2":
        print("\n📝 SUPABASE SETUP INSTRUCTIONS:\n")
        print("1. Go to: https://supabase.com")
        print("2. Create a new project")
        print("3. Go to Settings → Database")
        print("4. Copy the 'Connection string' (URI format)")
        print("\n" + "-"*70)
        
        conn_string = input("\nPaste your Supabase connection string here: ").strip()
        
        if not conn_string.startswith("postgresql://"):
            print("❌ Invalid connection string. Must start with 'postgresql://'")
            return False
        
        conn_string = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
        database_url = f"DATABASE_URL={conn_string}"
        
    elif choice == "3":
        print("\n📝 Enter your PostgreSQL connection string:")
        print("   Format: postgresql://user:password@host:port/database")
        
        conn_string = input("\nConnection string: ").strip()
        
        if "://" not in conn_string:
            print("❌ Invalid connection string format")
            return False
        
        if not conn_string.startswith("postgresql"):
            print("❌ Connection string must start with 'postgresql://'")
            return False
        
        if "+psycopg" not in conn_string:
            conn_string = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
        
        database_url = f"DATABASE_URL={conn_string}"
        
    elif choice == "4":
        print("\n🐳 Setting up local PostgreSQL with Docker...")
        print("   Container name: mealmind-postgres")
        print("   Database: mealmind")
        print("   Port: 5432")
        
        database_url = "DATABASE_URL=postgresql+psycopg://postgres:mealmind123@localhost:5432/mealmind"
        
        print("\nDocker command will be displayed after .env update")
        
    else:
        print("❌ Invalid choice")
        return False
    
    # Update .env file
    print("\n📝 Updating .env file...")
    if update_env_file(database_url):
        print("✅ .env file updated successfully!")
    else:
        print("❌ Failed to update .env file")
        return False
    
    # Show Docker command if option 4
    if choice == "4":
        print("\n🐳 Now run this Docker command:")
        print("-"*70)
        print("docker run --name mealmind-postgres `")
        print("  -e POSTGRES_PASSWORD=mealmind123 `")
        print("  -e POSTGRES_DB=mealmind `")
        print("  -p 5432:5432 `")
        print("  -d postgres:15")
        print("-"*70)
        
        run_docker = input("\nRun Docker command now? (y/n): ").strip().lower()
        if run_docker == 'y':
            import subprocess
            try:
                result = subprocess.run([
                    "docker", "run", "--name", "mealmind-postgres",
                    "-e", "POSTGRES_PASSWORD=mealmind123",
                    "-e", "POSTGRES_DB=mealmind",
                    "-p", "5432:5432",
                    "-d", "postgres:15"
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ PostgreSQL container started!")
                    print(f"   Container ID: {result.stdout.strip()}")
                else:
                    print(f"❌ Error: {result.stderr}")
                    return False
            except Exception as e:
                print(f"❌ Failed to start Docker container: {e}")
                return False
    
    # Next steps
    print("\n" + "="*70)
    print("✅ POSTGRESQL SETUP COMPLETE!")
    print("="*70)
    print("\nNext steps:")
    print("1. Migrate your existing SQLite data:")
    print("   python migrate_sqlite_to_postgres.py")
    print("\n2. Restart the backend:")
    print("   Stop current backend (Ctrl+C), then:")
    print("   python -m src.main")
    print("\n3. Test the application")
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
        sys.exit(1)
