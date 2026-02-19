# Deployment
# 배포

## Docker / 도커

### Quick Start / 빠른 시작

```bash
docker build -t salmalm .
docker run -p 18800:18800 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e SALMALM_BIND=0.0.0.0 \
  salmalm
```

### Docker Compose / 도커 컴포즈

```bash
# Edit docker-compose.yml with your API keys
# docker-compose.yml에 API 키를 입력하세요
docker-compose up -d
```

```yaml
version: "3.8"
services:
  salmalm:
    build: .
    ports:
      - "127.0.0.1:18800:18800"
      - "127.0.0.1:18801:18801"
    volumes:
      - ./data/memory:/app/memory
      - ./data/workspace:/app/workspace
      - ./data/uploads:/app/uploads
      - ./data/plugins:/app/plugins
    environment:
      - SALMALM_BIND=0.0.0.0
      # - ANTHROPIC_API_KEY=sk-...
    restart: unless-stopped
```

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir salmalm cryptography
RUN mkdir -p memory workspace uploads plugins
EXPOSE 18800 18801
ENV SALMALM_PORT=18800
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18800/api/health')" || exit 1
ENTRYPOINT ["python3", "-m", "salmalm"]
```

## systemd

Create `/etc/systemd/system/salmalm.service`:

`/etc/systemd/system/salmalm.service` 파일을 생성하세요:

```ini
[Unit]
Description=SalmAlm Personal AI Gateway
After=network.target

[Service]
Type=simple
User=salmalm
WorkingDirectory=/opt/salmalm
EnvironmentFile=/opt/salmalm/.env
ExecStart=/usr/bin/python3 -m salmalm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable salmalm
sudo systemctl start salmalm
sudo systemctl status salmalm
```

## Cloud Deployment / 클라우드 배포

### AWS EC2

```bash
# 1. Launch Ubuntu 22.04+ instance / EC2 인스턴스 실행
# 2. Install Python 3.10+ / 파이썬 설치
sudo apt update && sudo apt install -y python3 python3-pip

# 3. Install SalmAlm / SalmAlm 설치
pip install salmalm[crypto]

# 4. Configure / 설정
cp .env.example .env
nano .env  # Add API keys / API 키 추가

# 5. Start with systemd / systemd로 시작
sudo systemctl start salmalm
```

### Railway / Render / Fly.io

These platforms support Docker deployments. Use the provided `Dockerfile`.

이 플랫폼들은 Docker 배포를 지원합니다. 제공된 `Dockerfile`을 사용하세요.

Set environment variables in the platform dashboard.

플랫폼 대시보드에서 환경변수를 설정하세요.

### Reverse Proxy (Nginx) / 리버스 프록시

```nginx
server {
    listen 443 ssl;
    server_name ai.example.com;

    ssl_certificate /etc/letsencrypt/live/ai.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ai.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:18800;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Security Considerations / 보안 고려사항

!!! warning "Production Checklist / 프로덕션 체크리스트"

    - Always use HTTPS in production / 프로덕션에서 항상 HTTPS 사용
    - Set `SALMALM_BIND=127.0.0.1` behind reverse proxy / 리버스 프록시 뒤에서 바인드 주소 설정
    - Set vault password (`SALMALM_VAULT_PW`) / 볼트 비밀번호 설정
    - Use firewall rules / 방화벽 규칙 사용
    - Regular backups of `memory/`, `*.db`, `.vault.enc` / 정기 백업
