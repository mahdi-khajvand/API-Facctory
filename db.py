# db.py
import mysql.connector
import hashlib
import streamlit as st
from functools import wraps

DB_CONFIG = {
    "host": "localhost",
    "user": "root",         # یوزر MySQL خودت
    "password": "",      # پسورد MySQL
    "database": "service_manager"
}

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- Auth ---
def login(username: str, password: str) -> dict | None:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM users WHERE username=%s AND password_hash=%s AND is_active=1",
        (username, hash_password(password))
    )
    user = cur.fetchone()
    conn.close()
    return user

# --- مدیریت یوزر (فقط admin) ---
def create_user(username: str, password: str, role: str, created_by: str) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, role, created_by) VALUES (%s, %s, %s, %s)",
            (username, hash_password(password), role, created_by)
        )
        conn.commit()
        conn.close()
        return True
    except mysql.connector.IntegrityError:
        return False  # username تکراری

def deactivate_user(username: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active=0 WHERE username=%s", (username,))
    conn.commit()
    conn.close()
    return True

def list_users() -> list:
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, username, role, is_active, created_at, created_by FROM users")
    users = cur.fetchall()
    conn.close()
    return users
