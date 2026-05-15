# SonarQube Integration - Implementation Roadmap

## Overview
This repository includes SonarQube integration for continuous code quality and security analysis.

## Prerequisites
- Docker and Docker Compose installed
- Node.js (for frontend analysis)
- Python 3.11+ (for backend analysis)

## Setup Instructions

### Step 1: Start SonarQube Server
```bash
# Start SonarQube and MongoDB using Docker Compose
docker-compose up -d

# Wait for SonarQube to start (may take 2-3 minutes)
# Check status: docker-compose logs -f sonarqube
```

### Step 2: Initial SonarQube Configuration
1. Open browser and navigate to: http://localhost:9000
2. Default credentials:
   - Username: `admin`
   - Password: `admin`
3. You'll be prompted to change the password on first login

### Step 3: Generate Authentication Token
1. Login to SonarQube
2. Click on your profile (top right) → My Account
3. Go to Security tab
4. Generate a new token:
   - Name: `fullstack-app-token`
   - Type: `Project Analysis Token`
   - Click Generate
5. Copy the token and add it to `.env.sonar` file:
   ```
   SONAR_TOKEN=your_generated_token_here
   ```

### Step 4: Install SonarScanner

#### Option A: Using npm (recommended for this project)
```bash
npm install -g sonarqube-scanner
```

#### Option B: Download standalone scanner
```bash
# Linux/Mac
wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-5.0.1.3006-linux.zip
unzip sonar-scanner-cli-5.0.1.3006-linux.zip
export PATH=$PATH:$(pwd)/sonar-scanner-5.0.1.3006-linux/bin
```

### Step 5: Run Analysis

#### Manual Analysis
```bash
# Load environment variables
source .env.sonar

# Run SonarQube analysis
sonar-scanner \
  -Dsonar.projectKey=fullstack-app \
  -Dsonar.sources=. \
  -Dsonar.host.url=http://localhost:9000 \
  -Dsonar.login=$SONAR_TOKEN
```

#### Using npm script (after adding to package.json)
```bash
npm run sonar
```

### Step 6: View Results
1. Go to http://localhost:9000
2. Click on your project: `Full Stack Application`
3. Review:
   - Code Smells
   - Bugs
   - Vulnerabilities
   - Security Hotspots
   - Code Coverage (after setting up tests)
   - Code Duplications

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: SonarQube Analysis

on:
  push:
    branches:
      - main
      - develop
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  sonarqube:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0
      
      - name: SonarQube Scan
        uses: sonarsource/sonarqube-scan-action@master
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
```

### GitLab CI Example
```yaml
sonarqube-check:
  image: sonarsource/sonar-scanner-cli:latest
  variables:
    SONAR_USER_HOME: "${CI_PROJECT_DIR}/.sonar"
    GIT_DEPTH: "0"
  cache:
    key: "${CI_JOB_NAME}"
    paths:
      - .sonar/cache
  script:
    - sonar-scanner
  only:
    - merge_requests
    - main
    - develop
```

## Configuration Files

### sonar-project.properties
Main configuration file containing:
- Project identification
- Source code paths
- Exclusion patterns
- Test locations
- Language-specific settings

### docker-compose.yml
Defines services:
- **sonarqube**: Code analysis server (port 9000)
- **mongodb**: Database for the application (port 27017)

### .env.sonar
Environment variables for SonarQube connection:
- Server URL
- Authentication token
- Project key

## Quality Gates

SonarQube includes default quality gates. You can customize them:

1. Go to Quality Gates in SonarQube
2. Create a new gate or modify existing
3. Set conditions:
   - Coverage on new code > 80%
   - Duplicated lines on new code ≤ 3%
   - Maintainability rating on new code = A
   - Reliability rating on new code = A
   - Security rating on new code = A

## Best Practices

1. **Run analysis regularly**: Integrate with your CI/CD pipeline
2. **Fix issues incrementally**: Focus on new code first
3. **Set up test coverage**: Configure Jest (frontend) and pytest (backend)
4. **Review security hotspots**: Address security vulnerabilities promptly
5. **Monitor technical debt**: Keep track of code smells and refactor regularly

## Troubleshooting

### SonarQube won't start
```bash
# Check logs
docker-compose logs sonarqube

# Ensure sufficient memory (SonarQube needs ~2GB RAM)
# Restart services
docker-compose down
docker-compose up -d
```

### Analysis fails
```bash
# Check scanner version compatibility
sonar-scanner --version

# Verify token is correct
echo $SONAR_TOKEN

# Check network connectivity
curl http://localhost:9000/api/system/status
```

### Port conflicts
```bash
# If port 9000 is in use, modify docker-compose.yml:
# ports:
#   - "9001:9000"  # Use 9001 instead
```

## Additional Resources

- [SonarQube Documentation](https://docs.sonarqube.org/latest/)
- [SonarScanner CLI](https://docs.sonarqube.org/latest/analyzing-source-code/scanners/sonarscanner/)
- [Quality Gates](https://docs.sonarqube.org/latest/user-guide/quality-gates/)
- [Analysis Parameters](https://docs.sonarqube.org/latest/analyzing-source-code/analysis-parameters/)

## Maintenance

### Update SonarQube
```bash
# Backup data first
docker-compose down

# Pull latest image
docker-compose pull sonarqube

# Start with new version
docker-compose up -d
```

### Cleanup
```bash
# Stop and remove containers
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v
```
