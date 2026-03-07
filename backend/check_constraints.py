"""Check constraints on user_monthly_usage table"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)

with Session(engine) as session:
    # Check unique constraints
    result = session.execute(text("""
        SELECT conname, contype, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'user_monthly_usage'::regclass
    """)).fetchall()
    
    print("Constraints on user_monthly_usage:")
    for r in result:
        print(f"  {r[0]} ({r[1]}): {r[2]}")
    
    # Check indexes
    indexes = session.execute(text("""
        SELECT indexname, indexdef 
        FROM pg_indexes 
        WHERE tablename = 'user_monthly_usage'
    """)).fetchall()
    
    print("\nIndexes:")
    for i in indexes:
        print(f"  {i[0]}: {i[1]}")
