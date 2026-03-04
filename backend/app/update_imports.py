#!/usr/bin/env python3
"""
Script to update import statements after code reorganization.
Updates all app. imports to use the new directory structure.
"""

import os
import re
from pathlib import Path

def update_imports_in_file(file_path):
    """Update imports in a single file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Define import mappings (old -> new)
    import_replacements = {
        # Core imports
        'from app.config import': 'from app.core.config import',
        'from app.memory import': 'from app.core.memory import', 
        'from app.shadow_deployment import': 'from app.core.shadow_deployment import',
        
        # Model imports
        'from app.bulk_models import': 'from app.models.bulk_models import',
        'from app.models_supabase import': 'from app.models.models_supabase import',
        'from app.schemas import': 'from app.models.schemas import',
        'from app.schemas_supabase import': 'from app.models.schemas_supabase import',
        
        # Service imports  
        'from app.llm_service import': 'from app.services.llm_service import',
        'from app.bulk_processor import': 'from app.services.bulk_processor import',
        'from app.processor import': 'from app.services.processor import',
        'from app.bulk_embedding import': 'from app.services.bulk_embedding import',
        
        # Database imports
        'from app.auth_supabase import': 'from app.database.auth_supabase import',
        'from app.supabase_client import': 'from app.database.supabase_client import',
        'from app.database import': 'from app.database.database import',
        'from app.db_persistence import': 'from app.database.db_persistence import',
        
        # API imports
        'from app.bulk_api import': 'from app.api.bulk_api import',
        'from app.bulk_routes import': 'from app.api.bulk_routes import',
        
        # Worker imports
        'from app.bulk_worker import': 'from app.workers.bulk_worker import', 
        'from app.progress_tracker import': 'from app.workers.progress_tracker import',
        'from app.resource_tracker import': 'from app.workers.resource_tracker import',
    }
    
    # Apply replacements
    changes_made = False
    for old_import, new_import in import_replacements.items():
        if old_import in content:
            content = content.replace(old_import, new_import)
            changes_made = True
            print(f"  Updated: {old_import} -> {new_import}")
    
    # Write back if changes were made
    if changes_made and content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Updated {file_path}")
        return True
    
    return False

def main():
    """Main function to update all Python files."""
    app_dir = Path(__file__).parent
    print(f"Updating imports in: {app_dir}")
    
    # Find all Python files
    python_files = list(app_dir.rglob("*.py"))
    
    updated_count = 0
    for file_path in python_files:
        # Skip __pycache__ and this script itself
        if '__pycache__' in str(file_path) or file_path.name == 'update_imports.py':
            continue
        
        print(f"Checking: {file_path}")
        if update_imports_in_file(file_path):
            updated_count += 1
    
    print(f"\\n✅ Updated {updated_count} files")

if __name__ == "__main__":
    main()