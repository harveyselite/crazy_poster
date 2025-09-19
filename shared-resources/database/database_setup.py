"""
Crazy_poster Database Setup
Creates the SQLite database schema for the entire system
"""

import sqlite3
import os
from datetime import datetime

class DatabaseSetup:
    def __init__(self, db_path="crazy_poster.db"):
        self.db_path = db_path
        self.conn = None
    
    def connect(self):
        """Create database connection"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        
    def create_tables(self):
        """Create all required tables"""
        
        # Accounts table - stores Facebook account information
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_name TEXT UNIQUE NOT NULL,
                facebook_email TEXT UNIQUE NOT NULL,
                folder_path TEXT UNIQUE NOT NULL,
                status TEXT DEFAULT 'inactive',
                chrome_port INTEGER UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP,
                total_posts INTEGER DEFAULT 0,
                failed_posts INTEGER DEFAULT 0
            )
        ''')
        
        # Campaigns table - stores CSV upload campaigns
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_name TEXT NOT NULL,
                csv_filename TEXT NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_listings INTEGER DEFAULT 0,
                assigned_accounts TEXT,  -- JSON array of account IDs
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Listings table - stores individual vehicle listings
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                stock_type TEXT,
                platform TEXT DEFAULT 'facebook',
                title TEXT NOT NULL,
                vehicle_type TEXT,
                make TEXT,
                model TEXT,
                year INTEGER,
                mileage INTEGER,
                price DECIMAL(10,2),
                week_price DECIMAL(10,2),
                body_style TEXT,
                color_ext TEXT,
                color_int TEXT,
                condition TEXT,
                fuel TEXT,
                transmission TEXT,
                title_status TEXT,
                location TEXT,
                description TEXT,
                images TEXT,  -- JSON array of image URLs
                groups TEXT,  -- JSON array of Facebook groups
                hide_from_friends BOOLEAN DEFAULT 0,
                external_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')
        
        # Posting_history table - tracks all posting attempts
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS posting_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                listing_id INTEGER,
                campaign_id INTEGER,
                post_status TEXT DEFAULT 'pending',  -- pending, posted, failed, sold
                facebook_post_id TEXT,
                posted_at TIMESTAMP,
                scheduled_for TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                images_downloaded BOOLEAN DEFAULT 0,
                local_image_paths TEXT,  -- JSON array of local paths
                FOREIGN KEY (account_id) REFERENCES accounts (id),
                FOREIGN KEY (listing_id) REFERENCES listings (id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')
        
        # Schedules table - stores posting schedules
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                campaign_id INTEGER,
                day_of_week TEXT,  -- monday, tuesday, etc.
                time_slot TEXT,    -- 09:00, 14:30, etc.
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts (id),
                FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
            )
        ''')
        
        # Failed_posts table - detailed failure tracking
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS failed_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                posting_history_id INTEGER,
                account_id INTEGER,
                listing_id INTEGER,
                failure_reason TEXT,
                error_screenshot TEXT,  -- path to screenshot
                retry_scheduled_for TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (posting_history_id) REFERENCES posting_history (id),
                FOREIGN KEY (account_id) REFERENCES accounts (id),
                FOREIGN KEY (listing_id) REFERENCES listings (id)
            )
        ''')
        
        # System_settings table - global configuration
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_name TEXT UNIQUE NOT NULL,
                setting_value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        print("âœ“ All database tables created successfully")
    
    def create_indexes(self):
        """Create database indexes for better performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_accounts_email ON accounts(facebook_email)",
            "CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)",
            "CREATE INDEX IF NOT EXISTS idx_listings_campaign ON listings(campaign_id)",
            "CREATE INDEX IF NOT EXISTS idx_posting_history_account ON posting_history(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_posting_history_status ON posting_history(post_status)",
            "CREATE INDEX IF NOT EXISTS idx_posting_history_scheduled ON posting_history(scheduled_for)",
            "CREATE INDEX IF NOT EXISTS idx_schedules_active ON schedules(is_active)",
        ]
        
        for index_sql in indexes:
            self.conn.execute(index_sql)
        
        print("âœ“ Database indexes created successfully")
    
    def insert_default_settings(self):
        """Insert default system settings"""
        default_settings = [
            ("api_port", "8000"),
            ("default_post_interval", "6"),
            ("max_retry_attempts", "2"),
            ("chrome_base_port", "9222"),
            ("app_version", "1.0.0"),
            ("last_backup", ""),
        ]
        
        for setting_name, setting_value in default_settings:
            self.conn.execute('''
                INSERT OR IGNORE INTO system_settings (setting_name, setting_value)
                VALUES (?, ?)
            ''', (setting_name, setting_value))
        
        print("âœ“ Default settings inserted")
    
    def setup_database(self):
        """Complete database setup process"""
        try:
            self.connect()
            print("Setting up Crazy_poster database...")
            
            self.create_tables()
            self.create_indexes()
            self.insert_default_settings()
            
            self.conn.commit()
            print("âœ“ Database setup completed successfully!")
            
        except Exception as e:
            print(f"âœ— Database setup failed: {str(e)}")
            if self.conn:
                self.conn.rollback()
        
        finally:
            if self.conn:
                self.conn.close()

if __name__ == "__main__":
    # Run database setup
    db_setup = DatabaseSetup()
    db_setup.setup_database()
