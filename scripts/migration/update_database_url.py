"""
Quick script to update .env with your Neon PostgreSQL URL
"""

from pathlib import Path

def update_env():
    print("\n" + "="*70)
    print("UPDATE DATABASE_URL IN .ENV")
    print("="*70 + "\n")
    
    print("📋 After completing Neon signup, you'll see a connection string like:")
    print("   postgresql://user:password@ep-xxxxx.region.aws.neon.tech/neondb")
    print("\n" + "-"*70 + "\n")
    
    # Get connection string from user
    conn_string = input("Paste your Neon connection string here: ").strip()
    
    if not conn_string:
        print("❌ No connection string provided!")
        return False
    
    if not conn_string.startswith("postgresql://"):
        print("❌ Invalid connection string. Must start with 'postgresql://'")
        return False
    
    # Add psycopg driver
    if "+psycopg" not in conn_string:
        conn_string = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
        print("\n✅ Added '+psycopg' driver to URL")
    
    # Update .env file
    env_path = Path(".env")
    if not env_path.exists():
        print("❌ .env file not found!")
        return False
    
    # Read and update
    with open(env_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    updated = False
    new_lines = []
    
    for line in lines:
        if line.strip().startswith('DATABASE_URL='):
            # Comment out old line
            new_lines.append(f'# OLD: {line}')
            # Add new line
            new_lines.append(f'DATABASE_URL={conn_string}\n')
            updated = True
        elif line.strip().startswith('# OLD: DATABASE_URL='):
            # Skip old commented lines
            continue
        else:
            new_lines.append(line)
    
    if not updated:
        # Add at end if not found
        new_lines.append(f'\n# PostgreSQL Configuration\nDATABASE_URL={conn_string}\n')
    
    # Write back
    with open(env_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("\n" + "="*70)
    print("✅ SUCCESS! .env FILE UPDATED")
    print("="*70)
    print("\n📋 NEXT STEPS:")
    print("="*70)
    print("\n1️⃣  Migrate your existing data:")
    print("   python migrate_sqlite_to_postgres.py")
    print("\n2️⃣  Restart the backend:")
    print("   • Find the terminal running the backend")
    print("   • Press Ctrl+C to stop it")
    print("   • Run: python -m src.main")
    print("\n3️⃣  Test your application:")
    print("   • Open http://localhost:5173")
    print("   • Login with Swiggy OAuth")
    print("   • All features will sync with real Swiggy!")
    print("\n" + "="*70 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        update_env()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
