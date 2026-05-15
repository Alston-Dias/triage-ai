#!/bin/bash

echo "=================================="
echo "SonarQube Integration Verification"
echo "=================================="
echo ""

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    echo "   ✅ Docker is installed"
    docker --version
else
    echo "   ❌ Docker is not installed"
fi
echo ""

# Check Docker Compose
echo "2. Checking Docker Compose..."
if command -v docker-compose &> /dev/null; then
    echo "   ✅ Docker Compose is installed"
    docker-compose --version
else
    echo "   ❌ Docker Compose is not installed"
fi
echo ""

# Check Python
echo "3. Checking Python..."
if command -v python3 &> /dev/null; then
    echo "   ✅ Python is installed"
    python3 --version
else
    echo "   ❌ Python is not installed"
fi
echo ""

# Check Node.js
echo "4. Checking Node.js..."
if command -v node &> /dev/null; then
    echo "   ✅ Node.js is installed"
    node --version
else
    echo "   ❌ Node.js is not installed"
fi
echo ""

# Check project structure
echo "5. Checking project structure..."
if [ -f "docker-compose.yml" ]; then
    echo "   ✅ docker-compose.yml found"
else
    echo "   ❌ docker-compose.yml not found"
fi

if [ -f "sonar-project.properties" ]; then
    echo "   ✅ sonar-project.properties found"
else
    echo "   ❌ sonar-project.properties not found"
fi

if [ -d "frontend" ]; then
    echo "   ✅ frontend directory found"
else
    echo "   ❌ frontend directory not found"
fi

if [ -d "backend" ]; then
    echo "   ✅ backend directory found"
else
    echo "   ❌ backend directory not found"
fi
echo ""

# Check dependencies
echo "6. Checking dependencies..."
if [ -f "frontend/package.json" ]; then
    echo "   ✅ frontend/package.json found"
    if [ -d "frontend/node_modules" ]; then
        echo "   ✅ Frontend dependencies installed"
    else
        echo "   ⚠️  Frontend dependencies not installed (run: cd frontend && npm install)"
    fi
else
    echo "   ❌ frontend/package.json not found"
fi

if [ -f "backend/requirements.txt" ]; then
    echo "   ✅ backend/requirements.txt found"
fi
echo ""

# Check Docker services
echo "7. Checking Docker services..."
if docker-compose ps | grep -q "sonarqube"; then
    echo "   ✅ SonarQube service is defined"
else
    echo "   ℹ️  SonarQube service not running yet"
fi
echo ""

echo "=================================="
echo "Next Steps:"
echo "=================================="
echo "1. Install frontend dependencies: cd frontend && npm install"
echo "2. Install backend dependencies: cd backend && pip install -r requirements.txt"
echo "3. Start SonarQube: docker-compose up -d"
echo "4. Access SonarQube: http://localhost:9000 (admin/admin)"
echo "5. Generate token and add to .env.sonar"
echo "6. Run analysis: sonar-scanner"
echo ""
echo "For detailed instructions, see README_SONARQUBE.md"
echo "=================================="
