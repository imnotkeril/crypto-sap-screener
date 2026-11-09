# Server Deployment without Docker (SQLite + systemd + nginx)

Goal: Deploy once and run continuously on the server without local manual starts.

## 1) Backend (FastAPI) as a Service

### Requirements
- Linux server (Ubuntu/Debian)
- Python 3.10+

### Preparation
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip nginx
```

### Project Installation
```bash
sudo mkdir -p /opt/stat-arb
sudo chown -R $USER:$USER /opt/stat-arb
cd /opt/stat-arb
git clone <YOUR_REPO_URL> .
```

### Virtual Environment + Dependencies
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables
Create `/opt/stat-arb/backend/.env`:
```env
DATABASE_URL=sqlite:///./data/stat_arb.db
```

### systemd Unit
Create file `/etc/systemd/system/stat-arb-backend.service`:
```ini
[Unit]
Description=Stat Arb Backend (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/stat-arb/backend
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/stat-arb/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stat-arb-backend
sudo systemctl status stat-arb-backend --no-pager
```

Logs:
```bash
journalctl -u stat-arb-backend -f
```

## 2) Frontend (React) as Static Files via nginx

### Build Frontend
The server should have Node.js 18+. If not, install it using a convenient method (nvm/repository).

```bash
cd /opt/stat-arb/frontend
npm ci
npm run build
```

The build will create the `frontend/dist` folder.

### nginx Configuration
Create `/etc/nginx/sites-available/stat-arb`:
```nginx
server {
    listen 80;
    server_name _;

    root /opt/stat-arb/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Activate:
```bash
sudo ln -sf /etc/nginx/sites-available/stat-arb /etc/nginx/sites-enabled/stat-arb
sudo nginx -t
sudo systemctl restart nginx
```

## 3) What Will Be Stored
- SQLite file: `backend/data/stat_arb.db`
- Results of each screening run are saved as "session" + "all pairs"
- After backend restart, results are preserved
