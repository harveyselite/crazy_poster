import sqlite3
import os
import json
import shutil
from datetime import datetime

# Clean up any orphaned folders
account_path = "C:/Crazy_poster/account-instances/Account_001"
if os.path.exists(account_path):
    shutil.rmtree(account_path)
    print("Removed orphaned folder")

# Recreate the account properly
account_name = "Account_001"
facebook_email = "test1@gmail.com"

# Create folder structure
os.makedirs(f"{account_path}/config", exist_ok=True)
os.makedirs(f"{account_path}/browser-profile", exist_ok=True)
os.makedirs(f"{account_path}/temp-images", exist_ok=True)
os.makedirs(f"{account_path}/logs", exist_ok=True)
os.makedirs(f"{account_path}/campaign-data", exist_ok=True)
os.makedirs(f"{account_path}/posting-history", exist_ok=True)

# Create config
config = {
    "account_name": account_name,
    "facebook_email": facebook_email,
    "status": "inactive",
    "chrome_port": 9222,
    "created_at": datetime.now().isoformat()
}

with open(f"{account_path}/config/account.json", 'w') as f:
    json.dump(config, f, indent=2)

# Add to database
try:
    conn = sqlite3.connect("C:/Crazy_poster/shared-resources/database/crazy_poster.db")
    conn.execute('''
        INSERT INTO accounts (account_name, facebook_email, folder_path, chrome_port, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (account_name, facebook_email, account_path, 9222, "inactive", datetime.now()))
    conn.commit()
    conn.close()
    print("Account created and added to database")
except Exception as e:
    print(f"Database error: {e}")

print("Account setup complete!")
