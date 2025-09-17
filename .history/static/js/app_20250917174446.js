class RenderFlow {
        constructor() {
          this.ws = null;
          this.currentPage = 0;
          this.limit = 200; // Default to 200
          this.hiddenStatuses = new Set(); // Track hidden statuses
          this.starredFilter = false; // Track if showing only starred jobs
          this.jobs = [];
          this.stats = {};
          this.selectedJob = null;
          this.hoveredJob = null;

          this.initWebSocket();
          this.initEventListeners();
          this.loadJobs();
          this.loadStats();

          // Start timer for updating elapsed times
          this.startElapsedTimeUpdater();
        }

        getStatusIcon(status) {
          const icons = {
            inactive: "○",
            working: "⚙",
            complete: "✓",
            done: "◉",
            error: "✕",
            flagged: "⚠",
          };
          return icons[status] || "○";
        }

        formatElapsedTime(elapsedSeconds) {
          if (!elapsedSeconds) return "";

          const hours = Math.floor(elapsedSeconds / 3600);
          const minutes = Math.floor((elapsedSeconds % 3600) / 60);
          const seconds = elapsedSeconds % 60;

          if (hours > 0) {
            return `${hours}h ${minutes}m`;
          } else if (minutes > 0) {
            return `${minutes}m ${seconds}s`;
          } else {
            return `${seconds}s`;
          }
        }

        startElapsedTimeUpdater() {
          // Update elapsed times every second for working jobs
          setInterval(() => {
            this.updateElapsedTimes();
          }, 1000);
        }

        updateElapsedTimes() {
          // Update elapsed times for all rendering jobs without full re-render
          this.jobs.forEach((job) => {
            if (job.status === "rendering" && job.elapsed_time !== null) {
              job.elapsed_time += 1;
              // Update the DOM element
              const jobElement = document.querySelector(
                `[data-job-id="${job.id}"] .job-status`
              );
              if (jobElement) {
                const timeStr = this.formatElapsedTime(job.elapsed_time);
                const statusIcon = this.getStatusIcon("rendering");
                const workerLink = job.worker_url
                  ? `<a href="${job.worker_url}" target="_blank" class="worker-link" title="Open worker UI">▶</a>`
                  : "";

                jobElement.innerHTML = `
                  <div class="working-content">${statusIcon} Rendering</div>
                  <div class="working-right">
                    <span class="elapsed-time">${timeStr}</span>
                    ${workerLink}
                  </div>
                `;
              }
            }
          });
        }

        initWebSocket() {
          const protocol = location.protocol === "https:" ? "wss:" : "ws:";
          this.ws = new WebSocket(`${protocol}//${location.host}/ws`);

          this.ws.onopen = () => {
            this.updateConnectionStatus(true);
          };

          this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleWebSocketMessage(data);
          };

          this.ws.onclose = () => {
            this.updateConnectionStatus(false);
            // Reconnect after 3 seconds
            setTimeout(() => this.initWebSocket(), 3000);
          };

          this.ws.onerror = () => {
            this.updateConnectionStatus(false);
          };
        }

        updateConnectionStatus(connected) {
          const status = document.getElementById("connectionStatus");
          status.textContent = connected ? "● Connected" : "○ Disconnected";
          status.className = `connection-status ${
            connected ? "connected" : "disconnected"
          }`;
        }

        handleWebSocketMessage(data) {
          if (data.type === "job_update") {
            // Reload jobs to get complete updated data including elapsed_time and worker_url
            this.loadJobs();
            this.loadStats(); // Update stats
          }
        }

        initEventListeners() {
          // Status filter chips - click to hide/show status
          document.querySelectorAll(".status-chip").forEach((chip) => {
            chip.addEventListener("click", () => {
              const status = chip.dataset.status;

              if (status === "starred") {
                // Handle starred filter differently
                this.starredFilter = !this.starredFilter;
                if (this.starredFilter) {
                  chip.classList.add("active");
                } else {
                  chip.classList.remove("active");
                }
              } else {
                // Handle regular status filters
                if (this.hiddenStatuses.has(status)) {
                  this.hiddenStatuses.delete(status);
                  chip.classList.remove("hidden");
                } else {
                  this.hiddenStatuses.add(status);
                  chip.classList.add("hidden");
                }
              }

              this.renderJobs(); // Re-render with new filters
            });
          });

          // Jump to index
          document
            .getElementById("jumpToIndex")
            .addEventListener("keydown", (e) => {
              if (e.key === "Enter") {
                const index = parseInt(e.target.value);
                if (index && index >= 1 && index <= 100000) {
                  this.jumpToJob(index);
                }
              }
            });

          // Per page input - auto update on input
          const perPageInput = document.getElementById("perPageInput");
          perPageInput.addEventListener("input", (e) => {
            const newLimit = parseInt(e.target.value);
            if (newLimit && newLimit >= 1 && newLimit <= 10000) {
              this.limit = newLimit;
              this.currentPage = 0; // Reset to first page
              this.loadJobs();
            }
          });

          // Also handle Enter key for per page input
          perPageInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
              const newLimit = parseInt(e.target.value);
              if (newLimit && newLimit >= 1 && newLimit <= 10000) {
                this.limit = newLimit;
                this.currentPage = 0; // Reset to first page
                this.loadJobs();
              }
            }
          });

          // Pagination
          document.getElementById("prevBtn").addEventListener("click", () => {
            if (this.currentPage > 0) {
              this.currentPage--;
              this.loadJobs();
            }
          });

          document.getElementById("nextBtn").addEventListener("click", () => {
            this.currentPage++;
            this.loadJobs();
          });
        }

        async jumpToJob(index) {
          // Calculate which page the job would be on
          const jobsPerPage = this.limit;
          const page = Math.floor((index - 1) / jobsPerPage);
          this.currentPage = page;
          await this.loadJobs();

          // Select the job
          const job = this.jobs.find((j) => j.id === index);
          if (job) {
            this.selectJob(job);

            // Scroll to position the selected job at the top of the list
            setTimeout(() => {
              const jobElement = document.querySelector(
                `[data-job-id="${index}"]`
              );
              if (jobElement) {
                const container = document.getElementById("jobItems");
                if (container) {
                  // Calculate the position to scroll to
                  const elementTop = jobElement.offsetTop;
                  const containerTop = container.offsetTop;

                  // Scroll so the job appears at the top of the visible area
                  container.scrollTop = elementTop - containerTop;
                }
              }
            }, 100); // Small delay to ensure DOM is updated
          }
        }

        async loadJobs() {
          try {
            const params = new URLSearchParams({
              limit: this.limit,
              offset: this.currentPage * this.limit,
            });

            const response = await fetch(`/jobs?${params}`);
            const data = await response.json();
            this.jobs = data.jobs;
            this.renderJobs();
            this.updatePagination();
          } catch (error) {
            console.error("Failed to load jobs:", error);
          }
        }

        async loadStats() {
          try {
            const response = await fetch("/stats");
            const data = await response.json();
            this.stats = data.stats;
            this.updateStatusCounts();
          } catch (error) {
            console.error("Failed to load stats:", error);
          }
        }

        updateStatusCounts() {
          // Calculate total jobs
          const total =
            (this.stats.inactive || 0) +
            (this.stats.working || 0) +
            (this.stats.complete || 0) +
            (this.stats.done || 0) +
            (this.stats.error || 0) +
            (this.stats.flagged || 0);

          // Update total
          const totalElement = document.getElementById("totalJobs");
          if (totalElement) {
            totalElement.textContent = total.toLocaleString();
          }

          // Update individual counts
          const statusTypes = [
            "inactive",
            "working",
            "complete",
            "done",
            "error",
            "flagged",
          ];
          statusTypes.forEach((status) => {
            const countElement = document.getElementById(`count-${status}`);
            if (countElement && this.stats[status] !== undefined) {
              countElement.textContent = this.stats[status].toLocaleString();
            }
          });
        }

        renderJobs() {
          const container = document.getElementById("jobItems");

          if (this.jobs.length === 0) {
            container.innerHTML = '<div class="loading">No jobs found</div>';
            return;
          }

          const html = this.jobs
            .filter((job) => {
              // Apply starred filter if active
              if (this.starredFilter && !job.starred) {
                return false;
              }
              return true;
            })
            .map((job) => {
              const isHidden = this.hiddenStatuses.has(job.status);

              // Get status icon
              const statusIcon = this.getStatusIcon(job.status);

              // Format status display with elapsed time and worker link for rendering jobs
              let statusDisplay =
                job.status.charAt(0).toUpperCase() + job.status.slice(1);
              if (job.status === "rendering") {
                const timeStr =
                  job.elapsed_time !== null
                    ? this.formatElapsedTime(job.elapsed_time)
                    : "";
                const workerLink = job.worker_url
                  ? `<a href="${job.worker_url}" target="_blank" class="worker-link" title="Open worker UI">→</a>`
                  : "";

                statusDisplay = `
                  <div class="working-content">${statusIcon} Rendering</div>
                  <div class="working-right">
                    ${
                      timeStr
                        ? `<span class="elapsed-time">${timeStr}</span>`
                        : ""
                    }
                    ${workerLink}
                  </div>
                `;
              } else {
                statusDisplay = `${statusIcon} ${statusDisplay}`;
              }

              return `
                        <div class="job-item ${
                          this.selectedJob && this.selectedJob.id === job.id
                            ? "selected"
                            : ""
                        } ${isHidden ? "hidden" : ""}"
                             data-job-id="${job.id}"
                             onmouseenter="renderFlow.hoverJobById(${job.id})"
                             onclick="renderFlow.selectJobById(${job.id})">
                            <div class="job-index">${job.id}</div>
                            <div class="job-status ${
                              job.status
                            }">${statusDisplay}</div>
                            <div class="job-star ${
                              job.starred ? "starred" : "not-starred"
                            }" onclick="renderFlow.toggleJobStar(${
                job.id
              }); event.stopPropagation();" title="${
                job.starred ? "Remove star" : "Add star"
              }">⭐</div>
                        </div>
                    `;
            })
            .join("");

          container.innerHTML = html;
        }

        updatePagination() {
          const headerPageInfo = document.getElementById("headerPageInfo");
          const prevBtn = document.getElementById("prevBtn");
          const nextBtn = document.getElementById("nextBtn");
          const perPageInput = document.getElementById("perPageInput");

          const total = Math.ceil(100000 / this.limit);

          // Update the input value to match current limit
          perPageInput.value = this.limit;

          // Update header page info
          headerPageInfo.textContent = `${this.currentPage + 1} of ${total}`;

          prevBtn.disabled = this.currentPage === 0;
          nextBtn.disabled = this.jobs.length < this.limit;
        }

        selectJob(job) {
          this.selectedJob = job;
          this.renderJobs(); // Re-render to update selection
          this.renderJobDetail();
        }

        hoverJob(job) {
          // Update preview on hover without changing selection
          this.hoveredJob = job;
          this.renderJobDetail();
        }

        hoverJobById(jobId) {
          const job = this.jobs.find((j) => j.id === jobId);
          if (job) {
            this.hoverJob(job);
          }
        }

        selectJobById(jobId) {
          const job = this.jobs.find((j) => j.id === jobId);
          if (job) {
            this.selectJob(job);
          }
        }

        async renderJobDetail() {
          const container = document.getElementById("jobDetail");
          const job = this.hoveredJob || this.selectedJob;

          if (!job) {
            container.innerHTML = `
                        <div class="empty-state">
                            <div class="empty-icon">▦</div>
                            <h3>Select a job to view details</h3>
                            <p>Choose a job from the list to see its status, preview, and attributes</p>
                        </div>
                    `;
            return;
          }

          try {
            const response = await fetch(`/preview/${job.id}`);
            const previewData = await response.json();

            const html = `
                        <div class="job-detail-header">
                            <div class="job-title">Job #${job.id}</div>
                            <div class="job-meta">Attributes for job ${
                              job.id
                            }</div>
                        </div>

                        <div class="job-detail-content">
                            <div class="preview-section">
                                <div class="preview-image" id="previewImage-${
                                  job.id
                                }">
                                    <div class="no-preview">Loading preview...</div>
                                </div>
                                <div class="image-url-link">
                                    <a href="${
                                      previewData.image_url
                                    }" target="_blank" class="url-link">
                                        🔗 ${previewData.image_url}
                                    </a>
                                </div>
                            </div>

                            <div class="traits-section">
                                <div class="traits-title">Job Traits</div>
                                <div class="trait-item">
                                    <div class="trait-label">Scene</div>
                                    <div class="trait-value">${
                                      previewData.traits?.scene ||
                                      "Default Scene"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Resolution</div>
                                    <div class="trait-value">${
                                      previewData.traits?.resolution ||
                                      "1920x1080"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Frame Rate</div>
                                    <div class="trait-value">${
                                      previewData.traits?.frame_rate || "30"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Style</div>
                                    <div class="trait-value">${
                                      previewData.traits?.style || "Realistic"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Lighting</div>
                                    <div class="trait-value">${
                                      previewData.traits?.lighting || "Standard"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Camera Angle</div>
                                    <div class="trait-value">${
                                      previewData.traits?.camera_angle ||
                                      "Eye Level"
                                    }</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Status</div>
                                    <div class="trait-value">
                                        <span class="job-status ${
                                          job.status
                                        }">${this.getStatusIcon(job.status)} ${
              job.status.charAt(0).toUpperCase() + job.status.slice(1)
            }</span>
                                    </div>
                                </div>
                                ${
                                  job.worker_url
                                    ? `
                                <div class="trait-item">
                                    <div class="trait-label">Worker</div>
                                    <div class="trait-value">
                                        <a href="${job.worker_url}" target="_blank" class="worker-link-detail">→ ${job.worker_url}</a>
                                    </div>
                                </div>
                                `
                                    : ""
                                }
                                <div class="trait-item">
                                    <div class="trait-label">Updated</div>
                                    <div class="trait-value">${new Date(
                                      job.updated_at
                                    ).toLocaleString()}</div>
                                </div>
                                <div class="trait-item">
                                    <div class="trait-label">Star</div>
                                    <div class="trait-value">
                                        <button class="star-toggle ${
                                          job.starred ? "starred" : ""
                                        }" 
                                                onclick="renderFlow.toggleJobStar(${
                                                  job.id
                                                })"
                                                title="${
                                                  job.starred
                                                    ? "Remove star"
                                                    : "Star this job"
                                                }">
                                            ${
                                              job.starred
                                                ? "⭐ Starred"
                                                : "☆ Star"
                                            }
                                        </button>
                                    </div>
                                </div>
                                ${
                                  job.status === "done" ||
                                  job.status === "flagged"
                                    ? `
                                <div class="trait-item flagged-toggle-row">
                                    <div class="trait-label">Flag</div>
                                    <div class="trait-value">
                                        <button class="flagged-toggle ${
                                          job.status === "flagged"
                                            ? "flagged"
                                            : ""
                                        }" 
                                                onclick="renderFlow.toggleJobFlag(${
                                                  job.id
                                                }, '${job.status}')"
                                                title="${
                                                  job.status === "flagged"
                                                    ? "Remove flag"
                                                    : "Flag this job"
                                                }">
                                            ${
                                              job.status === "flagged"
                                                ? "⚠ Flagged"
                                                : "🏷 Flag"
                                            }
                                        </button>
                                    </div>
                                </div>
                                `
                                    : ""
                                }
                                <div class="trait-item reset-toggle-row">
                                    <div class="trait-label">Reset</div>
                                    <div class="trait-value">
                                        <button class="reset-toggle" 
                                                onclick="renderFlow.resetJob(${job.id})"
                                                title="Reset job to inactive status">
                                            🔄 Reset
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;

            container.innerHTML = html;

            // Load preview image
            this.loadPreviewImage(job.id, previewData.image_url);
          } catch (error) {
            console.error("Failed to load job details:", error);
          }
        }

        loadPreviewImage(jobId, imageUrl) {
          const previewElement = document.getElementById(
            `previewImage-${jobId}`
          );

          const img = new Image();
          img.onload = () => {
            previewElement.innerHTML = `<img src="${imageUrl}" alt="Job ${jobId}">`;
          };
          img.onerror = () => {
            previewElement.innerHTML =
              '<div class="no-preview">No preview available</div>';
          };
          img.src = imageUrl;
        }

        async toggleJobFlag(jobId, currentStatus) {
          try {
            const newStatus = currentStatus === "flagged" ? "done" : "flagged";
            const response = await fetch(`/job/${jobId}/status`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ status: newStatus }),
            });

            if (response.ok) {
              // Update the job in our local array
              const job = this.jobs.find((j) => j.id === jobId);
              if (job) {
                job.status = newStatus;
              }

              // Update hoveredJob and selectedJob if they're the same job
              if (this.hoveredJob && this.hoveredJob.id === jobId) {
                this.hoveredJob.status = newStatus;
              }
              if (this.selectedJob && this.selectedJob.id === jobId) {
                this.selectedJob.status = newStatus;
              }

              // Re-render the job details to update the button
              this.renderJobDetail();
              // Re-render the jobs list to update the status
              this.renderJobs();
              // Update the flagged popup if it's open
              this.updateFlaggedPopup();
            } else {
              console.error("Failed to toggle job flag");
            }
          } catch (error) {
            console.error("Error toggling job flag:", error);
          }
        }

        async resetJob(jobId) {
          try {
            // Get current job status for better user feedback
            const currentJob = this.jobs.find((j) => j.id === jobId) || 
                              this.hoveredJob || this.selectedJob;
            const currentStatus = currentJob ? currentJob.status : 'unknown';
            
            const response = await fetch(`/job/${jobId}/reset`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
            });

            if (response.ok) {
              // Update the job in our local array
              const job = this.jobs.find((j) => j.id === jobId);
              if (job) {
                job.status = "inactive";
                // Clear worker-related fields when resetting
                job.worker_url = null;
                job.start_time = null;
                job.elapsed_time = null;
              }

              // Update hoveredJob and selectedJob if they're the same job
              if (this.hoveredJob && this.hoveredJob.id === jobId) {
                this.hoveredJob.status = "inactive";
                this.hoveredJob.worker_url = null;
                this.hoveredJob.start_time = null;
                this.hoveredJob.elapsed_time = null;
              }
              if (this.selectedJob && this.selectedJob.id === jobId) {
                this.selectedJob.status = "inactive";
                this.selectedJob.worker_url = null;
                this.selectedJob.start_time = null;
                this.selectedJob.elapsed_time = null;
              }

              // Re-render the job details to update the display
              this.renderJobDetail();
              // Re-render the jobs list to update the status
              this.renderJobs();
              // Update stats to reflect the change
              this.loadStats();
              
              // Provide user feedback
              if (currentStatus === 'inactive') {
                console.log(`Job ${jobId} was already inactive, but reset completed successfully.`);
              } else {
                console.log(`Job ${jobId} reset from '${currentStatus}' to 'inactive'.`);
              }
            } else {
              console.error("Failed to reset job");
              alert("Failed to reset job. Please try again.");
            }
          } catch (error) {
            console.error("Error resetting job:", error);
            alert("Error resetting job. Please try again.");
          }
        }

        async toggleJobStar(jobId) {
          try {
            const response = await fetch(`/job/${jobId}/star`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
            });

            if (response.ok) {
              // Update the job in our local array
              const job = this.jobs.find((j) => j.id === jobId);
              if (job) {
                job.starred = !job.starred;
              }

              // Update hoveredJob and selectedJob if they're the same job
              if (this.hoveredJob && this.hoveredJob.id === jobId) {
                this.hoveredJob.starred = !this.hoveredJob.starred;
              }
              if (this.selectedJob && this.selectedJob.id === jobId) {
                this.selectedJob.starred = !this.selectedJob.starred;
              }

              // Re-render the job details to update the button
              this.renderJobDetail();
              // Re-render the jobs list if starred filter is active
              this.renderJobs();
            } else {
              console.error("Failed to toggle job star");
            }
          } catch (error) {
            console.error("Error toggling job star:", error);
          }
        }

        toggleFlaggedPopup(event) {
          event.stopPropagation();
          this.updateFlaggedPopup();
          this.showFlaggedPopup();
        }

        showFlaggedPopup() {
          const popup = document.getElementById("flaggedPopup");
          const overlay = document.getElementById("flaggedPopupOverlay");
          popup.style.display = "block";
          overlay.style.display = "block";
        }

        closeFlaggedPopup() {
          const popup = document.getElementById("flaggedPopup");
          const overlay = document.getElementById("flaggedPopupOverlay");
          popup.style.display = "none";
          overlay.style.display = "none";
        }

        updateFlaggedPopup() {
          const textarea = document.getElementById("flaggedPopupTextarea");
          const resetButton = document.getElementById("resetAllFlaggedBtn");
          const flaggedJobs = this.jobs.filter(
            (job) => job.status === "flagged"
          );

          if (flaggedJobs.length === 0) {
            textarea.value = "";
            textarea.placeholder = "No flagged jobs";
            if (resetButton) {
              resetButton.disabled = true;
              resetButton.textContent = "🔄 No Flagged Jobs to Reset";
            }
          } else {
            const jobIds = flaggedJobs.map((job) => job.id).join(", ");
            textarea.value = jobIds;
            textarea.placeholder = "";
            if (resetButton) {
              resetButton.disabled = false;
              resetButton.textContent = `🔄 Reset All Flagged Jobs (${flaggedJobs.length})`;
            }
          }
        }

        async resetAllFlaggedJobs() {
          const flaggedJobs = this.jobs.filter(
            (job) => job.status === "flagged"
          );
          
          if (flaggedJobs.length === 0) {
            console.log("No flagged jobs to reset");
            return;
          }

          console.log(`Starting reset of ${flaggedJobs.length} flagged jobs:`, flaggedJobs.map(j => `${j.id}(${j.status})`));

          const resetButton = document.getElementById("resetAllFlaggedBtn");
          if (resetButton) {
            resetButton.disabled = true;
            resetButton.textContent = "🔄 Resetting...";
          }

          try {
            const response = await fetch("/jobs/reset-flagged", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
            });

            if (response.ok) {
              const result = await response.json();
              console.log(`✅ Server response:`, result);
              console.log(`Successfully reset ${result.reset_count} flagged jobs to inactive status`);
              
              // Refresh the job list to show updated statuses
              await this.loadJobs();
              console.log("📋 Job list refreshed");
              
              // Update the flagged popup
              this.updateFlaggedPopup();
              console.log("🔄 Flagged popup updated");
              
              // Show success message (optional)
              if (result.reset_count > 0) {
                // Could add a toast notification here if desired
                console.log(`✅ Reset ${result.reset_count} flagged jobs to inactive status`);
              }
            } else {
              console.error("Failed to reset flagged jobs:", response.statusText);
              throw new Error("Reset failed");
            }
          } catch (error) {
            console.error("Error resetting flagged jobs:", error);
            // Re-enable button on error
            if (resetButton) {
              resetButton.disabled = false;
              resetButton.textContent = `🔄 Reset All Flagged Jobs (${flaggedJobs.length})`;
            }
          }
        }
      }

      const renderFlow = new RenderFlow();
    