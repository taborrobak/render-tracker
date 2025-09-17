#!/usr/bin/env python3
"""
Worker integration script for ComfyUI render queue
This script should be deployed with ComfyUI workers to communicate with the central tracker
"""
import requests
import json
import os
from typing import Optional

class RenderQueueClient:
    def __init__(self, tracker_url: str = "http://localhost:8000"):
        """
        Initialize the render queue client
        
        Args:
            tracker_url: URL of the central render tracker server
        """
        self.tracker_url = tracker_url.rstrip('/')
        
    def get_next_job(self) -> Optional[int]:
        """
        Get the next available job from the queue
        
        Returns:
            int: Job ID if available, None if no jobs available
        """
        try:
            response = requests.get(f"{self.tracker_url}/next-job", timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get('job_id')
        except Exception as e:
            print(f"Error getting next job: {e}")
            return None
    
    def update_job_status(self, job_id: int, status: str) -> bool:
        """
        Update the status of a job
        
        Args:
            job_id: The job ID to update
            status: New status (inactive, working, complete, done, error, flagged)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.tracker_url}/job/{job_id}/status",
                json={"status": status},
                timeout=30
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Error updating job {job_id} status to {status}: {e}")
            return False
    
    def mark_job_complete(self, job_id: int) -> bool:
        """Mark a job as complete"""
        return self.update_job_status(job_id, "complete")
    
    def mark_job_error(self, job_id: int) -> bool:
        """Mark a job as error"""
        return self.update_job_status(job_id, "error")
    
    def mark_job_done(self, job_id: int) -> bool:
        """Mark a job as done (downloaded)"""
        return self.update_job_status(job_id, "done")


# Example usage for ComfyUI custom node
def example_comfyui_integration():
    """
    Example of how to integrate this with a ComfyUI custom node
    """
    # Initialize client (adjust URL for your setup)
    client = RenderQueueClient("http://YOUR_TRACKER_SERVER:8000")
    
    # Get next job
    job_id = client.get_next_job()
    
    if job_id is None:
        print("No jobs available")
        return None
    
    print(f"Got job ID: {job_id}")
    
    # Use this job_id in your ComfyUI workflow
    # For example, as a seed or filename parameter
    
    return job_id


# Example usage for upload script integration
def example_upload_integration(filename: str, tracker_url: str):
    """
    Example of how to integrate this with upload scripts
    
    Args:
        filename: The uploaded filename (e.g., "123.png")
        tracker_url: URL of the tracker server
    """
    # Extract job ID from filename
    try:
        job_id = int(os.path.splitext(filename)[0])
        
        # Mark job as complete
        client = RenderQueueClient(tracker_url)
        success = client.mark_job_complete(job_id)
        
        if success:
            print(f"Marked job {job_id} as complete")
        else:
            print(f"Failed to mark job {job_id} as complete")
            
    except ValueError:
        print(f"Could not extract job ID from filename: {filename}")


if __name__ == "__main__":
    # Test the client
    client = RenderQueueClient()
    
    # Test getting next job
    job_id = client.get_next_job()
    print(f"Next job ID: {job_id}")
    
    if job_id:
        # Test updating status
        success = client.update_job_status(job_id, "working")
        print(f"Update status success: {success}")
