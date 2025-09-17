# Render Queue Tracker

A distributed job queue system for managing ComfyUI render jobs across multiple workers.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DEPLOYMENT SEPARATION                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📁 render_tracker/ (CENTRAL SERVER - NOT DEPLOYED)    │
│  ├── server.py              # FastAPI server            │
│  ├── database.py            # SQLite job database       │
│  ├── dashboard.html         # Web dashboard             │
│  ├── worker_client.py       # Worker integration lib    │
│  ├── start_tracker.sh       # Startup script            │
│  └── jobs.db               # SQLite database file       │
│                                                         │
│  📁 ComfyUI/ (DOCKERIZED & DEPLOYED TO WORKERS)        │
│  ├── [All ComfyUI files]                               │
│  ├── tabor_assets/                                     │
│  │   ├── upload_local.sh    # Updated with API calls   │
│  │   └── worker_client.py   # Copy of integration lib  │
│  └── custom_nodes/                                     │
│      └── job_queue_node.py  # Custom node for jobs     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## How It Works

1. **Central Server**: Run the tracker server on your main machine
2. **Workers**: Deploy ComfyUI with worker integration to remote machines
3. **Job Flow**:
   - Worker calls API to get next job ID
   - ComfyUI renders image with that ID as filename
   - Upload script uploads image and marks job complete
   - Download script marks job as done when downloaded locally

## Quick Start

### 1. Start the Central Tracker (Main Machine)

```bash
cd /home/tabor/render_tracker
./start_tracker.sh
```

This will:

- Install dependencies
- Initialize database with 100,000 jobs
- Start API server on port 8000
- Open web dashboard at http://localhost:8000

### 2. Deploy Workers (Remote Machines)

Copy these files to worker machines:

- `worker_client.py` - For ComfyUI integration
- Updated `upload_local.sh` - For status updates

### 3. ComfyUI Integration

Create a custom node that calls:

```python
from worker_client import RenderQueueClient

client = RenderQueueClient("http://YOUR_TRACKER_IP:8000")
job_id = client.get_next_job()  # Use this as filename/seed
```

## Job Status Flow

```
inactive → working → complete → done
     ↑        ↓         ↓
   reset   error    flagged
```

- **inactive**: Ready to be worked on
- **working**: Currently being rendered
- **complete**: Rendered and uploaded to Wasabi
- **done**: Downloaded to local machine
- **error**: Failed during rendering
- **flagged**: Needs re-rendering (manual flag)

## API Endpoints

- `GET /next-job` - Worker gets next job
- `POST /job/{id}/status` - Update job status
- `POST /job/{id}/flag` - Flag for re-render
- `GET /jobs` - List jobs with filtering
- `GET /stats` - Job statistics
- `GET /preview/{id}` - Preview image and traits

## Configuration

### Worker URLs

Update `worker_client.py` and `upload_local.sh` with your tracker server URL:

```python
# Change this to your tracker server IP
tracker_url = "http://YOUR_TRACKER_IP:8000"
```

### Image Storage

Images are stored at:

```
https://s3.eu-west-2.wasabisys.com/tabcorp-data/simtest4/{job_id}.png
```

### Traits Data

Place `traits.json` in the tracker directory for preview information.

## Features

- ✅ **Real-time Dashboard**: Live updates via WebSockets
- ✅ **Status Filtering**: Multi-select status filters
- ✅ **Job Management**: Flag/reset jobs via web interface
- ✅ **Preview System**: Image previews and traits display
- ✅ **Atomic Operations**: Race-condition-free job claiming
- ✅ **Simple Deployment**: Single SQLite file, no complex setup

## File Structure

```
render_tracker/
├── server.py              # Main FastAPI application
├── database.py            # SQLite database management
├── dashboard.html         # Web dashboard frontend
├── worker_client.py       # Worker integration library
├── start_tracker.sh       # Startup script
├── requirements.txt       # Python dependencies
├── jobs.db               # SQLite database (created on first run)
└── README.md             # This file
```
