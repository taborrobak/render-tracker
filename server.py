from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional, Set
import json
import asyncio
import os
from datetime import datetime, timezone
from database import JobDatabase

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, use regular env vars
    pass

app = FastAPI(title="Render Queue Tracker", version="1.0.0")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/renders", StaticFiles(directory="renders"), name="renders")

# Database instance
db = JobDatabase()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, data: dict):
        """Broadcast message to all connected clients"""
        message = json.dumps(data)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        
        # Remove disconnected connections
        for connection in disconnected:
            self.active_connections.discard(connection)

manager = ConnectionManager()

async def delete_wasabi_file(job_id: int) -> tuple[bool, str]:
    """
    Helper function to delete a file from Wasabi S3
    Returns (success: bool, message: str)
    """
    try:
        filename = f"{job_id}.png"
        
        # Try boto3 first (for Railway deployment)
        aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        
        if aws_access_key and aws_secret_key:
            # Use boto3 for Wasabi operations
            try:
                import boto3
                from botocore.exceptions import ClientError
                
                # Configure boto3 client for Wasabi
                s3_client = boto3.client(
                    's3',
                    endpoint_url=os.getenv("WASABI_ENDPOINT_URL", "https://s3.eu-west-2.wasabisys.com"),
                    aws_access_key_id=aws_access_key,
                    aws_secret_access_key=aws_secret_key,
                    region_name='eu-west-2'
                )
                
                bucket_name = os.getenv("WASABI_BUCKET_NAME", "tabcorp-data")
                prefix = os.getenv("WASABI_PREFIX", "simtest4")
                object_key = f"{prefix}/{filename}"
                
                # Check if file exists and delete it
                try:
                    s3_client.head_object(Bucket=bucket_name, Key=object_key)
                    # File exists, delete it
                    s3_client.delete_object(Bucket=bucket_name, Key=object_key)
                    return True, f"Successfully deleted {filename} from Wasabi (boto3)"
                except ClientError as e:
                    if e.response['Error']['Code'] == '404':
                        return False, f"File {filename} not found on Wasabi"
                    else:
                        raise e
                        
            except ImportError:
                return False, "boto3 not available"
            except Exception as e:
                return False, f"boto3 error: {str(e)}"
                
        else:
            # Fallback to rclone (for local development)
            import asyncio
            wasabi_path = f"wasabi:tabcorp-data/simtest4/{filename}"
            
            # Check if file exists on Wasabi
            check_cmd = ["rclone", "lsf", f"wasabi:tabcorp-data/simtest4/", "--include", filename]
            check_result = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await check_result.communicate()
            
            if check_result.returncode == 0 and stdout.decode().strip():
                # File exists, delete it
                delete_cmd = ["rclone", "delete", wasabi_path]
                delete_result = await asyncio.create_subprocess_exec(
                    *delete_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await delete_result.communicate()
                
                if delete_result.returncode == 0:
                    return True, f"Successfully deleted {filename} from Wasabi (rclone)"
                else:
                    return False, f"Failed to delete {filename} from Wasabi: {stderr.decode()}"
            else:
                return False, f"File {filename} not found on Wasabi"
    
    except Exception as e:
        return False, f"Error deleting file from Wasabi: {str(e)}"

def calculate_elapsed_time(start_time_str: Optional[str]) -> Optional[int]:
    """Calculate elapsed time in seconds from start_time string"""
    if not start_time_str:
        return None
    
    try:
        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        
        current_time = datetime.now(timezone.utc)
        elapsed = current_time - start_time
        return int(elapsed.total_seconds())
    except Exception:
        return None

# Pydantic models
class JobResponse(BaseModel):
    id: int
    status: str
    created_at: str
    updated_at: str
    start_time: Optional[str] = None
    elapsed_time: Optional[int] = None  # seconds
    worker_url: Optional[str] = None
    starred: bool = False

class JobsResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    limit: int

class StatsResponse(BaseModel):
    stats: dict

class JobUpdate(BaseModel):
    status: str

class ClaimJobRequest(BaseModel):
    worker_url: Optional[str] = None

class AuthRequest(BaseModel):
    password: str

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# API Routes

@app.get("/jobs")
async def get_jobs(limit: int = 20, offset: int = 0, status: Optional[str] = None):
    """Get paginated list of jobs"""
    try:
        jobs = db.get_jobs(limit=limit, offset=offset, status=status)
        total = db.get_total_count(status=status)
        
        job_responses = []
        for job in jobs:
            elapsed_time = None
            if job['status'] == 'working' and job.get('start_time'):
                elapsed_time = calculate_elapsed_time(job['start_time'])
            
            job_responses.append(JobResponse(
                id=job['id'],
                status=job['status'],
                created_at=job['created_at'],
                updated_at=job['updated_at'],
                start_time=job.get('start_time'),
                elapsed_time=elapsed_time,
                worker_url=job.get('worker_url'),
                starred=bool(job.get('starred', False))
            ))
        
        return JobsResponse(
            jobs=job_responses,
            total=total,
            page=offset // limit,
            limit=limit
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/stats")
async def get_stats():
    """Get job statistics"""
    try:
        stats = db.get_stats()
        return StatsResponse(stats=stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/job/{job_id}")
async def get_job(job_id: int):
    """Get specific job details"""
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        elapsed_time = None
        if job['status'] == 'working' and job.get('start_time'):
            elapsed_time = calculate_elapsed_time(job['start_time'])
        
        return JobResponse(
            id=job['id'],
            status=job['status'],
            created_at=job['created_at'],
            updated_at=job['updated_at'],
            start_time=job.get('start_time'),
            elapsed_time=elapsed_time,
            worker_url=job.get('worker_url'),
            starred=bool(job.get('starred', False))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/job/{job_id}/status")
async def update_job_status(job_id: int, job_update: JobUpdate):
    """Update job status"""
    try:
        success = db.update_job_status(job_id, job_update.status)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "status": job_update.status
        })
        
        return {"message": "Job status updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/job/{job_id}/claim")
async def claim_job(job_id: int, request: ClaimJobRequest = ClaimJobRequest()):
    """Claim a specific job"""
    try:
        success = db.claim_job(job_id, request.worker_url)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found or already claimed")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "status": "working"
        })
        
        return {"message": "Job claimed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/next-job")
async def get_next_job(request: ClaimJobRequest = ClaimJobRequest()):
    """Get the next available job and claim it"""
    try:
        job = db.get_next_job(request.worker_url)
        if not job:
            raise HTTPException(status_code=404, detail="No jobs available")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job['id'],
            "status": "working"
        })
        
        return JobResponse(
            id=job['id'],
            status=job['status'],
            created_at=job['created_at'],
            updated_at=job['updated_at'],
            start_time=job.get('start_time'),
            elapsed_time=calculate_elapsed_time(job.get('start_time')),
            worker_url=job.get('worker_url'),
            starred=bool(job.get('starred', False))
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/job/{job_id}/flag")
async def flag_job(job_id: int):
    """Flag a job"""
    try:
        success = db.update_job_status(job_id, "flagged")
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "status": "flagged"
        })
        
        return {"message": "Job flagged successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/job/{job_id}/star")
async def toggle_star(job_id: int):
    """Toggle the starred status of a job"""
    try:
        success = db.toggle_star(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "field": "starred"
        })
        
        return {"message": "Job star status toggled successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/job/{job_id}/reset")
async def reset_job(job_id: int):
    """Reset a job to inactive status and delete corresponding image from Wasabi"""
    try:
        wasabi_deletion_result = "Wasabi deletion disabled"
        
        # Check if Wasabi deletion is enabled and configured
        enable_wasabi = os.getenv("ENABLE_WASABI_DELETION", "true").lower() == "true"
        
        if enable_wasabi:
            success, message = await delete_wasabi_file(job_id)
            wasabi_deletion_result = message
            if success:
                print(f"✅ {message}")
            else:
                print(f"ℹ️ {message}")
        
        # Reset the job status (this happens regardless of Wasabi operation result)
        success = db.update_job_status(job_id, "inactive")
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "status": "inactive"
        })
        
        return {
            "message": "Job reset successfully",
            "wasabi_deletion": wasabi_deletion_result
        }
    except Exception as e:
        print(f"❌ Error in reset_job: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/reset-flagged")
async def reset_all_flagged_jobs():
    """Reset all flagged jobs to inactive status and delete corresponding images from Wasabi"""
    try:
        # Get all flagged jobs (use large limit to get all)
        flagged_jobs = db.get_jobs(limit=10000, status="flagged")
        reset_count = 0
        deleted_files = 0
        
        # Check if Wasabi deletion is enabled
        enable_wasabi = os.getenv("ENABLE_WASABI_DELETION", "true").lower() == "true"
        
        for job in flagged_jobs:
            job_id = job["id"]
            
            # Try to delete corresponding file from Wasabi if enabled
            if enable_wasabi:
                success, message = await delete_wasabi_file(job_id)
                if success:
                    deleted_files += 1
                    print(f"✅ {message}")
                else:
                    print(f"ℹ️ {message}")
            
            # Reset the job status
            success = db.update_job_status(job_id, "inactive")
            if success:
                reset_count += 1
                # Broadcast update to all connected clients for each job
                await manager.broadcast({
                    "type": "job_update",
                    "job_id": job_id,
                    "status": "inactive"
                })
        
        wasabi_message = f" and deleted {deleted_files} files from Wasabi" if enable_wasabi else ""
        return {
            "message": f"Successfully reset {reset_count} flagged jobs{wasabi_message}",
            "reset_count": reset_count,
            "deleted_files": deleted_files if enable_wasabi else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/reset-all")
async def reset_all_jobs():
    """Reset ALL jobs to inactive status and delete corresponding images from Wasabi"""
    import asyncio
    import os
    
    try:
        # Get all jobs (use large limit to get all)
        all_jobs = db.get_jobs(limit=10000)
        reset_count = 0
        deleted_files = 0
        
        # Check if Wasabi deletion is enabled
        enable_wasabi = os.getenv("ENABLE_WASABI_DELETION", "true").lower() == "true"
        
        for job in all_jobs:
            # Only reset jobs that are not already inactive
            if job["status"] != "inactive":
                job_id = job["id"]
                
                # Try to delete corresponding file from Wasabi if enabled
                if enable_wasabi:
                    try:
                        filename = f"{job_id}.png"
                        wasabi_path = f"wasabi:tabcorp-data/simtest4/{filename}"
                        
                        # Check if file exists on Wasabi
                        check_cmd = ["rclone", "lsf", f"wasabi:tabcorp-data/simtest4/", "--include", filename]
                        check_result = await asyncio.create_subprocess_exec(
                            *check_cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        stdout, stderr = await check_result.communicate()
                        
                        if check_result.returncode == 0 and stdout.decode().strip():
                            # File exists, delete it
                            delete_cmd = ["rclone", "delete", wasabi_path]
                            delete_result = await asyncio.create_subprocess_exec(
                                *delete_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            stdout, stderr = await delete_result.communicate()
                            
                            if delete_result.returncode == 0:
                                deleted_files += 1
                                print(f"✅ Successfully deleted {filename} from Wasabi")
                            else:
                                print(f"❌ Failed to delete {filename} from Wasabi: {stderr.decode()}")
                        
                    except Exception as e:
                        print(f"⚠️ Error checking/deleting Wasabi file for job {job_id}: {e}")
                        # Continue with job reset even if file deletion fails
                
                # Reset the job status
                success = db.update_job_status(job_id, "inactive")
                if success:
                    reset_count += 1
                    # Broadcast update to all connected clients for each job
                    await manager.broadcast({
                        "type": "job_update",
                        "job_id": job_id,
                        "status": "inactive"
                    })
        
        wasabi_message = f" and deleted {deleted_files} files from Wasabi" if enable_wasabi else ""
        return {
            "message": f"Successfully reset {reset_count} jobs to inactive status{wasabi_message}",
            "reset_count": reset_count,
            "deleted_files": deleted_files if enable_wasabi else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/jobs/reset-all")
async def reset_all_jobs():
    """Reset ALL jobs to inactive status and delete corresponding images from Wasabi"""
    try:
        # Get all jobs (use large limit to get all)
        all_jobs = db.get_jobs(limit=10000)
        reset_count = 0
        deleted_files = 0
        
        # Check if Wasabi deletion is enabled
        enable_wasabi = os.getenv("ENABLE_WASABI_DELETION", "true").lower() == "true"
        
        for job in all_jobs:
            # Only reset jobs that are not already inactive
            if job["status"] != "inactive":
                job_id = job["id"]
                
                # Try to delete corresponding file from Wasabi if enabled
                if enable_wasabi:
                    success, message = await delete_wasabi_file(job_id)
                    if success:
                        deleted_files += 1
                        print(f"✅ {message}")
                    else:
                        print(f"ℹ️ {message}")
                
                # Reset the job status
                success = db.update_job_status(job_id, "inactive")
                if success:
                    reset_count += 1
                    # Broadcast update to all connected clients for each job
                    await manager.broadcast({
                        "type": "job_update",
                        "job_id": job_id,
                        "status": "inactive"
                    })
        
        wasabi_message = f" and deleted {deleted_files} files from Wasabi" if enable_wasabi else ""
        return {
            "message": f"Successfully reset {reset_count} jobs to inactive status{wasabi_message}",
            "reset_count": reset_count,
            "deleted_files": deleted_files if enable_wasabi else 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/preview/{job_id}")
async def get_job_preview(job_id: int):
    # Load traits from traits.json
    traits_data = {}
    try:
        import json
        with open("traits.json", "r") as f:
            all_traits = json.load(f)
            # Use job_id to select traits from the dictionary
            trait_key = str(job_id)
            if trait_key in all_traits:
                traits_data = all_traits[trait_key]
            else:
                # If job_id not found, cycle through available keys
                available_keys = list(all_traits.keys())
                if available_keys:
                    key_index = (job_id - 1) % len(available_keys)
                    traits_data = all_traits[available_keys[key_index]]
                else:
                    # Use fallback if no traits available
                    raise KeyError("No traits available")
    except (FileNotFoundError, json.JSONDecodeError, IndexError, KeyError):
        # Fallback traits if file doesn't exist or is malformed
        traits_data = {
            "prompt": "a man wearing a gray t-shirt, short hair, in a urban alley background",
            "filename": "gray_tshirt_short_hair"
        }
    
    
    return {
        "traits": traits_data
    }

# Static file serving
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("dashboard.html")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}

# Authentication endpoint
@app.post("/auth")
async def authenticate(request: AuthRequest):
    """Authenticate user with password"""
    password = request.password
    # Get password from environment variable, fallback to default
    correct_password = os.getenv("RENDERFLOW_PASSWORD", "Babysweet22pfp")
    
    if password == correct_password:
        return {"authenticated": True, "message": "Authentication successful"}
    else:
        raise HTTPException(status_code=401, detail="Invalid password")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
