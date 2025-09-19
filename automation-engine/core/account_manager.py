"""
Crazy_poster Account Manager
Handles account creation, cloning, and management
"""

import os
import json
import shutil
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

class AccountManager:
    def __init__(self, base_path: str = "C:/Crazy_poster"):
        self.base_path = Path(base_path)
        self.accounts_path = self.base_path / "account-instances"
        self.template_path = self.accounts_path / "ACCOUNT_TEMPLATE"
        self.db_path = self.base_path / "shared-resources" / "database" / "crazy_poster.db"
        
    def get_next_chrome_port(self) -> int:
        """Get the next available Chrome remote debugging port"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT MAX(chrome_port) FROM accounts")
        result = cursor.fetchone()
        conn.close()
        
        if result[0] is None:
            return 9222  # Start from default port
        return result[0] + 1
    
    def create_account_folder(self, account_name: str, facebook_email: str) -> bool:
        """Create a new account folder by copying the template"""
        try:
            # Validate inputs
            if not account_name or not facebook_email:
                print("Error: Account name and Facebook email are required")
                return False
            
            # Check if account already exists
            account_path = self.accounts_path / account_name
            if account_path.exists():
                print(f"Error: Account folder '{account_name}' already exists")
                return False
            
            # Check if template exists
            if not self.template_path.exists():
                print(f"Error: Template folder not found at {self.template_path}")
                return False
            
            # Copy template to new account folder
            shutil.copytree(self.template_path, account_path)
            
            # Get unique Chrome port
            chrome_port = self.get_next_chrome_port()
            
            # Update account configuration
            config_path = account_path / "config" / "account.json"
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            config.update({
                "account_name": account_name,
                "facebook_email": facebook_email,
                "chrome_port": chrome_port,
                "status": "inactive",
                "created_at": datetime.now().isoformat()
            })
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Add account to database
            self.add_account_to_database(account_name, facebook_email, str(account_path), chrome_port)
            
            print(f"✓ Account '{account_name}' created successfully")
            print(f"  Folder: {account_path}")
            print(f"  Chrome Port: {chrome_port}")
            
            return True
            
        except Exception as e:
            print(f"✗ Failed to create account '{account_name}': {str(e)}")
            return False
    
    def add_account_to_database(self, account_name: str, facebook_email: str, 
                               folder_path: str, chrome_port: int):
        """Add new account to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                INSERT INTO accounts (
                    account_name, facebook_email, folder_path, 
                    chrome_port, status, created_at
                ) VALUES (?, ?, ?, ?, 'inactive', ?)
            ''', (account_name, facebook_email, folder_path, chrome_port, datetime.now()))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Database error: {str(e)}")
    
    def list_accounts(self) -> List[Dict]:
        """List all accounts with their status"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT id, account_name, facebook_email, status, 
                       chrome_port, last_activity, total_posts, failed_posts
                FROM accounts 
                ORDER BY account_name
            ''')
            
            accounts = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return accounts
            
        except Exception as e:
            print(f"Error listing accounts: {str(e)}")
            return []
    
    def delete_account(self, account_name: str, confirm: bool = False) -> bool:
        """Delete an account folder and database entry"""
        if not confirm:
            print("This action will permanently delete the account and all its data.")
            response = input(f"Are you sure you want to delete '{account_name}'? (yes/no): ")
            if response.lower() != 'yes':
                print("Account deletion cancelled")
                return False
        
        try:
            # Remove from database first
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("DELETE FROM accounts WHERE account_name = ?", (account_name,))
            
            if cursor.rowcount == 0:
                print(f"Account '{account_name}' not found in database")
                conn.close()
                return False
            
            conn.commit()
            conn.close()
            
            # Remove folder
            account_path = self.accounts_path / account_name
            if account_path.exists():
                shutil.rmtree(account_path)
            
            print(f"✓ Account '{account_name}' deleted successfully")
            return True
            
        except Exception as e:
            print(f"✗ Failed to delete account '{account_name}': {str(e)}")
            return False
    
    def clone_account(self, source_account: str, new_account_name: str, 
                     new_facebook_email: str) -> bool:
        """Clone an existing account with new credentials"""
        try:
            source_path = self.accounts_path / source_account
            if not source_path.exists():
                print(f"Source account '{source_account}' not found")
                return False
            
            # Create the clone
            new_path = self.accounts_path / new_account_name
            if new_path.exists():
                print(f"Account '{new_account_name}' already exists")
                return False
            
            # Copy source to new location (excluding browser profile)
            shutil.copytree(source_path, new_path)
            
            # Clear browser profile data to avoid Facebook detection
            browser_profile_path = new_path / "browser-profile"
            if browser_profile_path.exists():
                shutil.rmtree(browser_profile_path)
                browser_profile_path.mkdir()
            
            # Clear sensitive data
            self.clear_account_data(new_path)
            
            # Update configuration
            chrome_port = self.get_next_chrome_port()
            config_path = new_path / "config" / "account.json"
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            config.update({
                "account_name": new_account_name,
                "facebook_email": new_facebook_email,
                "chrome_port": chrome_port,
                "status": "inactive",
                "total_posts": 0,
                "failed_posts": 0,
                "last_activity": "",
                "created_at": datetime.now().isoformat()
            })
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Add to database
            self.add_account_to_database(new_account_name, new_facebook_email, 
                                       str(new_path), chrome_port)
            
            print(f"✓ Account '{new_account_name}' cloned from '{source_account}'")
            return True
            
        except Exception as e:
            print(f"✗ Failed to clone account: {str(e)}")
            return False
    
    def clear_account_data(self, account_path: Path):
        """Clear sensitive data from cloned account"""
        try:
            # Clear posting history
            status_file = account_path / "posting-history" / "status.json"
            default_status = {
                "active_campaigns": [],
                "posting_queue": [],
                "completed_posts": [],
                "failed_posts": [],
                "sold_listings": [],
                "repost_queue": []
            }
            
            with open(status_file, 'w') as f:
                json.dump(default_status, f, indent=2)
            
            # Clear logs
            log_file = account_path / "logs" / "automation.log"
            if log_file.exists():
                log_file.write_text("")
            
            # Clear temporary images
            temp_images = account_path / "temp-images"
            if temp_images.exists():
                for file in temp_images.glob("*"):
                    if file.is_file():
                        file.unlink()
            
        except Exception as e:
            print(f"Warning: Could not clear all account data: {str(e)}")
    
    def get_account_config(self, account_name: str) -> Optional[Dict]:
        """Get account configuration"""
        try:
            config_path = self.accounts_path / account_name / "config" / "account.json"
            if not config_path.exists():
                return None
            
            with open(config_path, 'r') as f:
                return json.load(f)
        
        except Exception as e:
            print(f"Error reading account config: {str(e)}")
            return None
    
    def update_account_status(self, account_name: str, status: str):
        """Update account status in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('''
                UPDATE accounts 
                SET status = ?, last_activity = ? 
                WHERE account_name = ?
            ''', (status, datetime.now(), account_name))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error updating account status: {str(e)}")

if __name__ == "__main__":
    # CLI interface for testing
    import sys
    
    manager = AccountManager()
    
    if len(sys.argv) < 2:
        print("Usage: python account_manager.py [create|list|delete|clone]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "create":
        if len(sys.argv) != 4:
            print("Usage: python account_manager.py create <account_name> <facebook_email>")
            sys.exit(1)
        
        account_name = sys.argv[2]
        facebook_email = sys.argv[3]
        manager.create_account_folder(account_name, facebook_email)
    
    elif command == "list":
        accounts = manager.list_accounts()
        print("\nCrazy_poster Accounts:")
        print("-" * 80)
        for acc in accounts:
            print(f"Name: {acc['account_name']:<20} Email: {acc['facebook_email']:<30} Status: {acc['status']}")
    
    elif command == "delete":
        if len(sys.argv) != 3:
            print("Usage: python account_manager.py delete <account_name>")
            sys.exit(1)
        
        account_name = sys.argv[2]
        manager.delete_account(account_name)
    
    elif command == "clone":
        if len(sys.argv) != 5:
            print("Usage: python account_manager.py clone <source_account> <new_account> <new_email>")
            sys.exit(1)
        
        source = sys.argv[2]
        new_account = sys.argv[3]
        new_email = sys.argv[4]
        manager.clone_account(source, new_account, new_email)
    
    else:
        print("Unknown command. Available: create, list, delete, clone")