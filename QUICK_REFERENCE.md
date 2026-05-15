# Quick Reference Guide

## 🚀 Get Started in 5 Minutes

### 1. Start SonarQube
```bash
docker-compose up -d
```
Wait 2-3 minutes for SonarQube to start, then go to http://localhost:9000

### 2. Login to SonarQube
- URL: http://localhost:9000
- Username: `admin`
- Password: `admin`
- Change password when prompted

### 3. Generate Token
1. Click profile icon (top right)
2. My Account → Security
3. Generate Token
4. Copy token and paste into `.env.sonar`:
   ```bash
   SONAR_TOKEN=your_token_here
   ```

### 4. Install Dependencies
```bash
# Frontend
cd frontend && npm install && cd ..

# Backend
cd backend && pip install -r requirements.txt && cd ..
```

### 5. Run SonarQube Analysis
```bash
# Install scanner globally
npm install -g sonarqube-scanner

# Run analysis
sonar-scanner
```

### 6. View Results
Go to http://localhost:9000 and click on "fullstack-app" project

---

## 📁 Project Structure

```
/app/
├── docker-compose.yml              # SonarQube + MongoDB
├── sonar-project.properties        # SonarQube config
├── .env.sonar                      # SonarQube credentials
│
├── frontend/                       # React app
│   ├── src/
│   │   ├── App.js                  # Main component (35 lines)
│   │   ├── components/             # UI components
│   │   │   ├── DataGrid.js
│   │   │   ├── TabNavigation.js
│   │   │   ├── ErrorMessage.js
│   │   │   └── LoadingSpinner.js
│   │   └── hooks/                  # Custom hooks
│   │       └── useDataFetching.js
│   ├── package.json
│   └── .env
│
├── backend/                        # FastAPI app
│   ├── server.py                   # API server
│   ├── tests/
│   │   └── test_server.py
│   ├── requirements.txt
│   └── .env
│
└── Documentation/
    ├── README.md                   # Main documentation
    ├── README_SONARQUBE.md         # SonarQube guide
    ├── IMPLEMENTATION_ROADMAP.md   # Implementation plan
    ├── CODE_QUALITY_IMPROVEMENTS.md
    └── CODE_REVIEW_FIXES_SUMMARY.md
```

---

## 🧪 Testing

### Backend Tests
```bash
cd backend
pytest
pytest --cov=. --cov-report=xml  # with coverage
```

### Frontend Tests
```bash
cd frontend
npm test                           # interactive
npm test -- --watchAll=false       # run once
npm test -- --coverage             # with coverage
```

---

## 🎯 Key Commands

| Task | Command |
|------|---------|
| Start SonarQube | `docker-compose up -d` |
| Stop SonarQube | `docker-compose down` |
| View SonarQube logs | `docker-compose logs -f sonarqube` |
| Start backend | `cd backend && python server.py` |
| Start frontend | `cd frontend && npm start` |
| Run analysis | `sonar-scanner` |
| Lint frontend | `cd frontend && npm run lint` |
| Test backend | `cd backend && pytest` |
| Test frontend | `cd frontend && npm test` |
| Verify setup | `./verify-setup.sh` |

---

## 📊 Application URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:3000 | N/A |
| Backend API | http://localhost:8001 | N/A |
| API Docs | http://localhost:8001/docs | N/A |
| SonarQube | http://localhost:9000 | admin/admin |
| MongoDB | localhost:27017 | N/A |

---

## 🔧 Configuration Files

### `.env.sonar` (SonarQube)
```env
SONAR_HOST_URL=http://localhost:9000
SONAR_TOKEN=<generate_from_sonarqube>
SONAR_PROJECT_KEY=fullstack-app
```

### `backend/.env` (Backend)
```env
MONGO_URL=mongodb://localhost:27017/appdb
PORT=8001
```

### `frontend/.env` (Frontend)
```env
REACT_APP_BACKEND_URL=http://localhost:8001/api
```

---

## ✅ Code Quality Status

| Metric | Status |
|--------|--------|
| Linting errors | ✅ 0 |
| Critical issues | ✅ 0 |
| Hook dependencies | ✅ Fixed |
| Function length | ✅ Optimized (35 lines) |
| Test coverage | ✅ Comprehensive (15+ tests) |
| Production console logs | ✅ Removed |
| Components | ✅ Modular (5 components) |
| Custom hooks | ✅ 1 (useDataFetching) |

---

## 🐛 Troubleshooting

### SonarQube won't start
```bash
docker-compose logs sonarqube
# Check for memory issues (needs 2GB RAM)
docker-compose restart sonarqube
```

### Port already in use
```bash
# Check what's using port 9000
lsof -i :9000
# Kill process or modify docker-compose.yml
```

### Backend connection error
```bash
# Verify backend is running
curl http://localhost:8001/api/health
# Check environment variables
cat frontend/.env
```

### Frontend build errors
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

---

## 📚 Documentation Map

| Document | Purpose |
|----------|---------|
| **README.md** | General project overview |
| **README_SONARQUBE.md** | Complete SonarQube setup guide |
| **IMPLEMENTATION_ROADMAP.md** | Implementation phases |
| **CODE_QUALITY_IMPROVEMENTS.md** | Detailed code refactoring |
| **CODE_REVIEW_FIXES_SUMMARY.md** | Executive summary of fixes |
| **QUICK_REFERENCE.md** | This file - quick commands |

---

## 🎯 Next Steps

1. ✅ **Setup Complete** - All files in place
2. ⏩ **Start SonarQube** - Run docker-compose up -d
3. ⏩ **Generate Token** - Login and create token
4. ⏩ **Run Analysis** - Execute sonar-scanner
5. ⏩ **Review Results** - Check quality metrics
6. ⏩ **Set Quality Gates** - Define thresholds
7. ⏩ **CI/CD Integration** - Add to pipeline

---

## 💡 Tips

- First SonarQube start takes 2-3 minutes
- Token is required for analysis
- Run tests before analysis for coverage data
- Check logs if services don't start
- Use `verify-setup.sh` to check prerequisites

---

## 📞 Need Help?

- Check detailed guides in documentation folder
- Review troubleshooting section above
- Check SonarQube logs: `docker-compose logs -f`
- Test backend: `curl http://localhost:8001/api/health`
- Run verification: `./verify-setup.sh`

---

**Quick Start:** `docker-compose up -d` → Login to http://localhost:9000 → Generate token → `sonar-scanner` → Review results ✨
