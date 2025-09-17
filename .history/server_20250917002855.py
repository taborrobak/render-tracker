from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional, Set
import json
import asyncio
from database import JobDatabase

app = FastAPI(title="Render Queue Tracker", version="1.0.0")

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

# Pydantic models
class JobResponse(BaseModel):
    id: int
    status: str
    created_at: str
    updated_at: str
    start_time: Optional[str] = None
    elapsed_time: Optional[int] = None  # seconds

class JobsResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    page: int
    limit: int

class StatsResponse(BaseModel):
    stats: dict

class JobUpdate(BaseModel):
    status: str

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
        
        job_responses = [
            JobResponse(
                id=job['id'],
                status=job['status'],
                created_at=job['created_at'],
                updated_at=job['updated_at']
            ) for job in jobs
        ]
        
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
        
        return JobResponse(
            id=job['id'],
            status=job['status'],
            created_at=job['created_at'],
            updated_at=job['updated_at']
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
async def claim_job(job_id: int):
    """Claim a specific job"""
    try:
        success = db.claim_job(job_id)
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
async def get_next_job():
    """Get the next available job and claim it"""
    try:
        job = db.get_next_job()
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
            updated_at=job['updated_at']
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

@app.post("/job/{job_id}/reset")
async def reset_job(job_id: int):
    """Reset a job to inactive status"""
    try:
        success = db.update_job_status(job_id, "inactive")
        if not success:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Broadcast update to all connected clients
        await manager.broadcast({
            "type": "job_update",
            "job_id": job_id,
            "status": "inactive"
        })
        
        return {"message": "Job reset successfully"}
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
            "scene": "Default Scene",
            "resolution": "1920x1080", 
            "frame_rate": "30",
            "style": "Realistic",
            "lighting": "Standard",
            "camera_angle": "Eye Level"
        }
    
    return {
        "image_url": f"https://picsum.photos/800/600?random={job_id}",
        "traits": traits_data
    }

# Static file serving
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return FileResponse("/home/tabor/render_tracker/dashboard.html")

# Health check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
