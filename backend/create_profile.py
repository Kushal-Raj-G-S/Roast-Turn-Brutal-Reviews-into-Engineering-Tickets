"""Create profile for existing logged-in user."""
from app.config import config
from sqlalchemy import create_engine, text

engine = create_engine(config.DATABASE_URL)
conn = engine.connect()

# Get existing user from auth.users
user = conn.execute(text('SELECT id, email FROM auth.users LIMIT 1')).fetchone()

if user:
    print(f'Found user: {user[1]} (ID: {user[0]})')
    
    # Create profile
    conn.execute(text("""
        INSERT INTO profiles (id, email, full_name, provider)
        VALUES (:id, :email, :name, :provider)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            full_name = EXCLUDED.full_name,
            provider = EXCLUDED.provider
    """), {"id": str(user[0]), "email": user[1], "name": "Kushal Raj", "provider": "google"})
    
    # Create user statistics
    conn.execute(text("""
        INSERT INTO user_statistics (user_id)
        VALUES (:user_id)
        ON CONFLICT (user_id) DO NOTHING
    """), {"user_id": str(user[0])})
    
    conn.commit()
    print('✅ Profile and statistics created!')
else:
    print('No users found. Please login first.')

conn.close()
