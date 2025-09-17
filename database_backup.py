import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict

class JobDatabase:
    def __init__(self, db_path: str = "jobs.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize database with jobs table and populate with 100,000 jobs"""
        with self.get_connection() as conn:
            # Create jobs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY,
                    status TEXT DEFAULT 'inactive',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Check if jobs are already populated
            count = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            
            if count == 0:
                print("Populating database with 100,000 jobs...")
                # Insert jobs 1-100000 with inactive status
                jobs_data = [(i, 'inactive') for i in range(1, 100001)]
                conn.executemany(
                    "INSERT INTO jobs (id, status) VALUES (?, ?)", 
                    jobs_data
                )
                print("Database populated successfully!")
    
    def get_next_job(self) -> Optional[int]:
        """Get next inactive job and mark as working atomically"""
        with self.get_connection() as conn:
            # Get first inactive job
            result = conn.execute(
                "SELECT id FROM jobs WHERE status = 'inactive' ORDER BY id LIMIT 1"
            ).fetchone()
            
            if result:
                job_id = result['id']
                # Mark as working
                conn.execute(
                    "UPDATE jobs SET status = 'working', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (job_id,)
                )
                return job_id
            return None
    
    def update_job_status(self, job_id: int, status: str) -> bool:
        """Update job status"""
        valid_statuses = ['inactive', 'working', 'complete', 'done', 'error', 'flagged']
        if status not in valid_statuses:
            return False
            
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, job_id)
            )
            return cursor.rowcount > 0
    
    def get_jobs(self, status_filter: List[str] = None, limit: int = 1000, offset: int = 0) -> List[Dict]:
        """Get jobs with optional status filtering"""
        with self.get_connection() as conn:
            if status_filter:
                placeholders = ','.join('?' * len(status_filter))
                query = f"""
                    SELECT id, status, updated_at 
                    FROM jobs 
                    WHERE status IN ({placeholders})
                    ORDER BY id 
                    LIMIT ? OFFSET ?
                """
                params = status_filter + [limit, offset]
            else:
                query = """
                    SELECT id, status, updated_at 
                    FROM jobs 
                    ORDER BY id 
                    LIMIT ? OFFSET ?
                """
                params = [limit, offset]
            
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
    
    def get_job_stats(self) -> Dict[str, int]:
        """Get count of jobs by status"""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
            ).fetchall()
            return {row['status']: row['count'] for row in rows}
    
    def flag_job(self, job_id: int) -> bool:
        """Flag a job for re-rendering"""
        return self.update_job_status(job_id, 'flagged')
    
    def reset_job(self, job_id: int) -> bool:
        """Reset a job back to inactive"""
        return self.update_job_status(job_id, 'inactive')

if __name__ == "__main__":
    # Test the database
    db = JobDatabase()
    print("Database initialized!")
    print("Job stats:", db.get_job_stats())
