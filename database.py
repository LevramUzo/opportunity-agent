import sqlite3
import os
from passlib.context import CryptContext

DB_PATH = "opportunities.db"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL,
            nationality TEXT DEFAULT 'Nigerian',
            education TEXT DEFAULT 'BSc Physics',
            field TEXT DEFAULT 'AI / Machine Learning',
            status TEXT DEFAULT 'NYSC',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Saved opportunities table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            organization TEXT,
            type TEXT,
            deadline TEXT,
            funding TEXT,
            eligibility TEXT,
            description TEXT,
            url TEXT NOT NULL,
            relevance_score REAL,
            match_reason TEXT,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def hash_password(password: str) -> str:
    # bcrypt has 72-byte limit, truncate if needed
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    return pwd_context.hash(password_bytes.decode('utf-8'))

def verify_password(password: str, hash: str) -> bool:
    return pwd_context.verify(password, hash)

# Run this when module loads
init_db()