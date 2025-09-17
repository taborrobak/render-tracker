#!/bin/bash

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔═══════════════════════════════════╗${NC}"
echo -e "${BLUE}║     RENDER QUEUE TRACKER v1.0     ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════╝${NC}"

# Check if we're in the right directory
if [ ! -f "server.py" ] || [ ! -f "database.py" ]; then
    echo -e "${RED}❌ Please run this script from the render_tracker directory${NC}"
    exit 1
fi

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${BLUE}📦 Installing dependencies...${NC}"
    pip3 install -r requirements.txt || {
        echo -e "${RED}❌ Failed to install dependencies${NC}"
        exit 1
    }
fi

# Initialize database
echo -e "${BLUE}🗄️  Initializing database...${NC}"
python3 database.py || {
    echo -e "${RED}❌ Failed to initialize database${NC}"
    exit 1
}

echo -e "${GREEN}✅ Database initialized successfully${NC}"

# Start the server
echo -e "${BLUE}🚀 Starting render queue tracker server...${NC}"
echo -e "${GREEN}📊 Dashboard will be available at: http://localhost:8000${NC}"
echo -e "${GREEN}🔗 API documentation at: http://localhost:8000/docs${NC}"
echo -e "${BLUE}Press Ctrl+C to stop the server${NC}"
echo ""

python3 server.py
