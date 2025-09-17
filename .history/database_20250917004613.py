import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict
import random

class JobDatabase:
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database with jobs table and populate with 100,000 jobs if empty"""
        with self.get_connection() as conn:
            # Create jobs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    status TEXT DEFAULT 'inactive',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    start_time TIMESTAMP NULL,
                    worker_url TEXT NULL
                )
            """)
            
            # Add start_time column if it doesn't exist (for existing databases)
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN start_time TIMESTAMP NULL")
            except sqlite3.OperationalError:
                # Column already exists
                pass
                
            # Add worker_url column if it doesn't exist (for existing databases)
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN worker_url TEXT NULL")
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
            # Check if we need to populate
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            if count == 0:
                print("Populating database with 100,000 jobs...")
                # Generate statuses with realistic distribution
                statuses = ['inactive'] * 85000 + ['working'] * 8000 + ['complete'] * 4000 + ['done'] * 2000 + ['error'] * 800 + ['flagged'] * 200
                random.shuffle(statuses)
                
                # Insert jobs in batches
                batch_size = 1000
                jobs_data = []
                for i in range(100000):
                    status = statuses[i]
                    created_time = datetime.now(timezone.utc).isoformat()
                    updated_time = created_time
                    jobs_data.append((i + 1, status, created_time, updated_time))
                    
                    if len(jobs_data) >= batch_size:
                        conn.executemany(
                            "INSERT INTO jobs (id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                            jobs_data
                        )
                        jobs_data = []
                
                # Insert remaining jobs
                if jobs_data:
                    conn.executemany(
                        "INSERT INTO jobs (id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                        jobs_data
                    )
                
                conn.commit()
                print("Database populated successfully!")
    
    def get_next_job(self) -> Optional[Dict]:
        """Get next available job and mark it as 'working'"""
        with self.get_connection() as conn:
            # Use transaction to prevent race conditions
            job = conn.execute(
                "SELECT id, status, created_at, updated_at FROM jobs WHERE status = 'inactive' ORDER BY id LIMIT 1"
            ).fetchone()
            
            if job:
                # Mark as working
                conn.execute(
                    "UPDATE jobs SET status = 'working', updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), job['id'])
                )
                conn.commit()
                return dict(job)
            return None
    
    def update_job_status(self, job_id: int, status: str) -> bool:
        """Update job status"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.now(timezone.utc).isoformat(), job_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_jobs(self, limit: int = 20, offset: int = 0, status: Optional[str] = None) -> List[Dict]:
        """Get paginated list of jobs"""
        with self.get_connection() as conn:
            if status:
                jobs = conn.execute(
                    "SELECT id, status, created_at, updated_at, start_time, worker_url FROM jobs WHERE status = ? ORDER BY id LIMIT ? OFFSET ?",
                    (status, limit, offset)
                ).fetchall()
            else:
                jobs = conn.execute(
                    "SELECT id, status, created_at, updated_at, start_time, worker_url FROM jobs ORDER BY id LIMIT ? OFFSET ?",
                    (limit, offset)
                ).fetchall()
            return [dict(job) for job in jobs]
    
    def get_total_count(self, status: Optional[str] = None) -> int:
        """Get total count of jobs"""
        with self.get_connection() as conn:
            if status:
                count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()[0]
            else:
                count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            return count
    
    def get_job_by_id(self, job_id: int) -> Optional[Dict]:
        """Get specific job by ID"""
        with self.get_connection() as conn:
            job = conn.execute(
                "SELECT id, status, created_at, updated_at, start_time FROM jobs WHERE id = ?",
                (job_id,)
            ).fetchone()
            return dict(job) if job else None
    
    def claim_job(self, job_id: int) -> bool:
        """Claim a specific job (mark as working)"""
        with self.get_connection() as conn:
            current_time = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "UPDATE jobs SET status = 'working', updated_at = ?, start_time = ? WHERE id = ? AND status = 'inactive'",
                (current_time, current_time, job_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def update_job_status(self, job_id: int, status: str) -> bool:
        """Update job status and clear start_time if not working"""
        with self.get_connection() as conn:
            current_time = datetime.now(timezone.utc).isoformat()
            if status == 'working':
                # Set start_time if moving to working status
                cursor = conn.execute(
                    "UPDATE jobs SET status = ?, updated_at = ?, start_time = ? WHERE id = ?",
                    (status, current_time, current_time, job_id)
                )
            else:
                # Clear start_time if moving away from working status
                cursor = conn.execute(
                    "UPDATE jobs SET status = ?, updated_at = ?, start_time = NULL WHERE id = ?",
                    (status, current_time, job_id)
                )
            conn.commit()
            return cursor.rowcount > 0
    
    def get_stats(self) -> Dict[str, int]:
        """Get job statistics by status"""
        with self.get_connection() as conn:
            stats = {}
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
            ).fetchall()
            for row in rows:
                stats[row['status']] = row['count']
            return stats
    
    def get_job_stats(self) -> Dict[str, int]:
        """Alias for get_stats for backward compatibility"""
        return self.get_stats()
