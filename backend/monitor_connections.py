"""
Database Connection Pool Management Script

This script helps monitor and manage database connection pools
to prevent and debug connection exhaustion issues.

Usage:
    python monitor_connections.py [command]
    
Commands:
    status   - Show current connection pool status
    dispose  - Dispose all connections and recreate pool
    restart  - Restart the application with fresh connections
    test     - Test database connectivity
"""

import logging
import time
from datetime import datetime
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_pool_status():
    """Check and display current connection pool status."""
    try:
        from app.api.bulk_api import get_engine_instance
        
        engine = get_engine_instance()
        if not engine:
            print("❌ Database engine not initialized")
            return False
            
        pool = engine.pool
        
        print(f"🔍 Database Connection Pool Status - {datetime.now()}")
        print(f"   Pool Size: {pool.size()}")
        print(f"   Checked Out: {pool.checkedout()}")
        print(f"   Checked In: {pool.checkedin()}")
        print(f"   Overflow: {pool.overflow()}")
        print(f"   Invalid: {pool.invalid()}")
        
        # Check if pool is near exhaustion
        total_connections = pool.size() + pool.overflow()
        used_connections = pool.checkedout()
        utilization = (used_connections / total_connections) * 100 if total_connections > 0 else 0
        
        print(f"   Utilization: {utilization:.1f}%")
        
        if utilization > 80:
            print("⚠️  HIGH UTILIZATION WARNING - Connection pool is near exhaustion")
        elif utilization > 60:
            print("🟡 MEDIUM UTILIZATION - Monitor closely")
        else:
            print("✅ HEALTHY - Connection pool has available capacity")
            
        return True
        
    except Exception as e:
        print(f"❌ Error checking pool status: {e}")
        return False


def dispose_connections():
    """Dispose all connections and recreate the pool."""
    try:
        from app.api.bulk_api import get_engine_instance
        
        engine = get_engine_instance()
        if not engine:
            print("❌ Database engine not initialized")
            return False
            
        print("🔄 Disposing all database connections...")
        engine.dispose()
        print("✅ All connections disposed successfully")
        
        # Test that we can reconnect
        print("🔄 Testing reconnection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Reconnection successful")
            
        return True
        
    except Exception as e:
        print(f"❌ Error disposing connections: {e}")
        return False


def test_connectivity():
    """Test database connectivity with timing."""
    try:
        from app.api.bulk_api import get_engine_instance
        
        engine = get_engine_instance()
        if not engine:
            print("❌ Database engine not initialized")
            return False
            
        print("🔍 Testing database connectivity...")
        
        start_time = time.time()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT NOW(), VERSION()"))
            row = result.fetchone()
            
        end_time = time.time()
        
        print(f"✅ Connection successful in {(end_time - start_time)*1000:.2f}ms")
        print(f"   Server time: {row[0]}")
        print(f"   PostgreSQL version: {row[1]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Database connectivity test failed: {e}")
        return False


def main():
    import sys
    
    if len(sys.argv) < 2:
        command = "status"
    else:
        command = sys.argv[1].lower()
    
    if command == "status":
        check_pool_status()
    elif command == "dispose":
        dispose_connections()
    elif command == "test":
        test_connectivity()  
    elif command == "restart":
        print("🔄 Restarting connection pool...")
        if dispose_connections():
            time.sleep(2)
            check_pool_status()
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: status, dispose, test, restart")


if __name__ == "__main__":
    main()