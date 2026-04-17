# GCP 인프라 배포 계획

> 작성일: 2026-04-17  
> Firebase 프로젝트 `ordinance-builder` 이미 생성됨 → GCP 프로젝트 연결부터 시작

---

## 전제 조건

| 항목 | 상태 | 비고 |
|------|------|------|
| Firebase 프로젝트 | ✅ 완료 | `ordinance-builder` |
| Firebase Web App 설정 | ✅ 완료 | `VITE_FIREBASE_*` 값 확보됨 |
| Google 로그인 활성화 | ❓ 확인 필요 | Firebase 콘솔 → Authentication |
| GCP 프로젝트 연결 | ❌ 미완료 | Firebase 프로젝트에 GCP 연결 필요 |
| Cloud SQL | ❌ 미완료 | |
| Neo4j AuraDB | ❌ 미완료 | 현재 로컬 Docker 사용 중 |
| Secret Manager | ❌ 미완료 | |
| Cloud Run | ❌ 미완료 | |
| Firebase Hosting | ❌ 미완료 | |

---

## Phase 0: 사전 준비

### 0-1. gcloud CLI 로그인 및 프로젝트 설정

```bash
# GCP 로그인
gcloud auth login
gcloud auth application-default login

# Firebase 프로젝트와 연결된 GCP 프로젝트 ID 확인 후 설정
# (Firebase 콘솔 → 프로젝트 설정 → 일반 → '프로젝트 ID' 확인)
gcloud config set project ordinance-builder

# 현재 설정 확인
gcloud config list
```

### 0-2. 필요 API 일괄 활성화

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  vpcaccess.googleapis.com \
  servicenetworking.googleapis.com
```

---

## Phase 1: Cloud SQL (PostgreSQL 17)

### 1-1. 인스턴스 생성

```bash
gcloud sql instances create ordinance-db \
  --database-version=POSTGRES_17 \
  --tier=db-g1-small \
  --region=asia-northeast3 \
  --storage-type=SSD \
  --storage-size=10GB \
  --backup-start-time=03:00 \
  --retained-backups-count=7 \
  --retained-transaction-log-days=7 \
  --no-assign-ip \
  --network=default
```

> `--no-assign-ip --network=default`: Public IP 없이 Private IP로만 접속 (보안)  
> Cloud Run → Cloud SQL 연결은 Cloud SQL Auth Proxy (Serverless VPC Access) 경유

### 1-2. 데이터베이스 및 사용자 생성

```bash
# DB 생성
gcloud sql databases create ordinance_builder \
  --instance=ordinance-db

# 전용 앱 유저 생성 (강력한 비밀번호 사용)
CLOUD_SQL_PASSWORD=$(openssl rand -base64 24)
echo "Cloud SQL Password: $CLOUD_SQL_PASSWORD"  # Secret Manager 등록 전 메모

gcloud sql users create app_user \
  --instance=ordinance-db \
  --password=$CLOUD_SQL_PASSWORD
```

### 1-3. Cloud SQL 연결 정보 확인

```bash
# Private IP 확인 (Secret Manager에 등록할 POSTGRES_URL 구성에 필요)
gcloud sql instances describe ordinance-db \
  --format="value(ipAddresses[0].ipAddress)"

# Connection name 확인 (Cloud Run --add-cloudsql-instances 파라미터)
gcloud sql instances describe ordinance-db \
  --format="value(connectionName)"
# 예: ordinance-builder:asia-northeast3:ordinance-db
```

### 1-4. Serverless VPC Access 커넥터 생성

Cloud Run → Cloud SQL Private IP 접속을 위해 필요합니다.

```bash
gcloud compute networks vpc-access connectors create ordinance-connector \
  --region=asia-northeast3 \
  --subnet=default \
  --subnet-project=ordinance-builder \
  --min-instances=2 \
  --max-instances=10
```

---

## Phase 2: Neo4j AuraDB 전환

로컬 Docker Neo4j → Neo4j AuraDB Professional로 전환합니다.

### 2-1. AuraDB 인스턴스 생성

1. [https://console.neo4j.io](https://console.neo4j.io) 접속
2. **New Instance** → **AuraDB Professional** 선택
   - Region: `asia-pacific-northeast` (asia-northeast3 가장 근접)
   - Name: `ordinance-db`
3. 생성 완료 후 **Connection URI**, **Username**, **Password** 기록

> ⚠️ 비밀번호는 생성 시 1회만 표시됩니다. 반드시 즉시 기록하세요.

### 2-2. 데이터 마이그레이션

로컬 Neo4j에 데이터가 있는 경우 덤프 후 AuraDB에 임포트합니다.

```bash
# 로컬 Neo4j 덤프 (Docker 컨테이너가 실행 중인 상태에서)
docker exec ordinance_builder-neo4j-1 \
  neo4j-admin database dump neo4j --to-path=/tmp/neo4j-dump

docker cp ordinance_builder-neo4j-1:/tmp/neo4j-dump ./neo4j-dump

# AuraDB에는 neo4j-admin upload 또는 콘솔의 Import 기능 사용
# (AuraDB Professional은 파일 업로드 지원)
```

데이터가 없는 경우 (처음 배포) Phase 7의 ETL 파이프라인으로 AuraDB에 직접 적재합니다.

---

## Phase 3: Secret Manager 등록

모든 민감 환경 변수를 Secret Manager에 등록합니다.

```bash
# GOOGLE_API_KEY
echo -n "AIzaSyDfz9LQmOEUJ1Z7iSe_sfcRHBYfsT03NDQ" | \
  gcloud secrets create GOOGLE_API_KEY --data-file=-

# ANTHROPIC_API_KEY
echo -n "<your-anthropic-key>" | \
  gcloud secrets create ANTHROPIC_API_KEY --data-file=-

# OPENAI_API_KEY
echo -n "<your-openai-key>" | \
  gcloud secrets create OPENAI_API_KEY --data-file=-

# NEO4J_URI (AuraDB URI)
echo -n "neo4j+s://<instance-id>.databases.neo4j.io" | \
  gcloud secrets create NEO4J_URI --data-file=-

# NEO4J_USER
echo -n "neo4j" | \
  gcloud secrets create NEO4J_USER --data-file=-

# NEO4J_PASSWORD (AuraDB 비밀번호)
echo -n "<auradb-password>" | \
  gcloud secrets create NEO4J_PASSWORD --data-file=-

# POSTGRES_URL (Cloud SQL Private IP 사용)
# 형식: postgresql://app_user:<password>@<private-ip>:5432/ordinance_builder
echo -n "postgresql://app_user:${CLOUD_SQL_PASSWORD}@<private-ip>:5432/ordinance_builder" | \
  gcloud secrets create POSTGRES_URL --data-file=-

# LAW_API_KEY
echo -n "qorwlsaud1" | \
  gcloud secrets create LAW_API_KEY --data-file=-
```

### Cloud Run 서비스 계정에 Secret Manager 접근 권한 부여

```bash
# Cloud Run 전용 서비스 계정 생성
gcloud iam service-accounts create ordinance-backend-sa \
  --display-name="Ordinance Builder Backend"

SA_EMAIL="ordinance-backend-sa@ordinance-builder.iam.gserviceaccount.com"

# Secret Manager 접근 권한
gcloud projects add-iam-policy-binding ordinance-builder \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/secretmanager.secretAccessor"

# Cloud SQL 접속 권한
gcloud projects add-iam-policy-binding ordinance-builder \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"
```

---

## Phase 4: Firebase Authentication 확인

Firebase 프로젝트가 이미 생성되어 있으므로 인증 설정만 확인합니다.

1. [Firebase 콘솔](https://console.firebase.google.com/project/ordinance-builder) 접속
2. **Authentication** → **Sign-in method** → **Google** 활성화 확인
3. **Authentication** → **Settings** → **승인된 도메인** 확인
   - Firebase Hosting 배포 후 `ordinance-builder.web.app` 자동 추가됨
   - 커스텀 도메인 사용 시 수동 추가 필요

### 백엔드용 Firebase 서비스 계정 (Cloud Run ADC)

Cloud Run에서는 `FIREBASE_CREDENTIALS_PATH` 없이 **Application Default Credentials**로 자동 인증됩니다.  
단, Cloud Run 서비스 계정에 Firebase 권한을 부여해야 합니다.

```bash
# Firebase Admin SDK 사용을 위한 IAM 역할 추가
gcloud projects add-iam-policy-binding ordinance-builder \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/firebase.sdkAdminServiceAgent"
```

---

## Phase 5: Artifact Registry + Cloud Run 배포

### 5-1. Artifact Registry 저장소 생성

```bash
gcloud artifacts repositories create ordinance-backend \
  --repository-format=docker \
  --location=asia-northeast3 \
  --description="Ordinance Builder Backend Images"
```

### 5-2. 이미지 빌드 및 푸시

프로젝트 루트(`d:\Project\Ordinance_Builder`)에서 실행합니다.

```bash
# Docker 인증 설정
gcloud auth configure-docker asia-northeast3-docker.pkg.dev

IMAGE="asia-northeast3-docker.pkg.dev/ordinance-builder/ordinance-backend/app"

# Cloud Build로 빌드 (로컬 Docker 없이도 가능)
gcloud builds submit \
  --tag "${IMAGE}:latest" \
  --timeout=20m
```

### 5-3. Cloud Run 배포

```bash
CONN_NAME="ordinance-builder:asia-northeast3:ordinance-db"
IMAGE="asia-northeast3-docker.pkg.dev/ordinance-builder/ordinance-backend/app:latest"

gcloud run deploy ordinance-backend \
  --image="${IMAGE}" \
  --region=asia-northeast3 \
  --platform=managed \
  --service-account="${SA_EMAIL}" \
  \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=40 \
  --cpu=2 \
  --memory=2Gi \
  --timeout=300 \
  --cpu-boost \
  \
  --add-cloudsql-instances="${CONN_NAME}" \
  --vpc-connector=ordinance-connector \
  --vpc-egress=private-ranges-only \
  \
  --set-secrets="\
GOOGLE_API_KEY=GOOGLE_API_KEY:latest,\
ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,\
OPENAI_API_KEY=OPENAI_API_KEY:latest,\
NEO4J_URI=NEO4J_URI:latest,\
NEO4J_USER=NEO4J_USER:latest,\
NEO4J_PASSWORD=NEO4J_PASSWORD:latest,\
POSTGRES_URL=POSTGRES_URL:latest" \
  \
  --set-env-vars="\
CORS_ORIGINS=https://ordinance-builder.web.app,\
LLM_INTENT=gemini,\
LLM_DRAFTING=anthropic,\
LLM_REVIEWER=anthropic,\
LLM_LEGAL=openai,\
MAX_INTERVIEW_TURNS=5,\
LOG_LEVEL=INFO,\
DEBUG_MODE=false"
```

### 5-4. Cloud Run URL 확인

```bash
BACKEND_URL=$(gcloud run services describe ordinance-backend \
  --region=asia-northeast3 \
  --format="value(status.url)")
echo "Backend URL: $BACKEND_URL"
```

---

## Phase 6: Firebase Hosting 배포 (프론트엔드)

### 6-1. Firebase CLI 설치 및 로그인

```bash
npm install -g firebase-tools
firebase login
```

### 6-2. 프론트엔드 빌드

`d:\Project\Ordinance_Builder\frontend` 디렉터리에서 실행합니다.

```bash
cd frontend

# .env.production 작성
cat > .env.production << 'EOF'
VITE_FIREBASE_API_KEY=AIzaSyDnC6_YhjV8Ff4tgH6LEdIHEwLYLm2dVQs
VITE_FIREBASE_AUTH_DOMAIN=ordinance-builder.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=ordinance-builder
EOF

# 프로덕션 빌드
npm run build
```

### 6-3. Firebase Hosting 초기화 (최초 1회)

```bash
# 프로젝트 루트에서 실행
cd ..
firebase init hosting
```

프롬프트 응답:
- **Project**: `ordinance-builder` 선택
- **Public directory**: `frontend/dist`
- **Single-page app**: `Yes`
- **GitHub auto-deploy**: `No`

### 6-4. firebase.json 구성

`firebase init hosting` 완료 후 `firebase.json`을 아래 내용으로 교체합니다.

```json
{
  "hosting": {
    "public": "frontend/dist",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      {
        "source": "/api/**",
        "run": {
          "serviceId": "ordinance-backend",
          "region": "asia-northeast3"
        }
      },
      {
        "source": "**",
        "destination": "/index.html"
      }
    ]
  }
}
```

> `/api/**` 요청을 Firebase Hosting이 Cloud Run으로 프록시합니다.  
> 프론트엔드의 `fetch('/api/v1/...')` 코드는 변경 없이 동작합니다.

### 6-5. 배포

```bash
firebase deploy --only hosting --project ordinance-builder
```

배포 완료 후 URL: `https://ordinance-builder.web.app`

---

## Phase 7: ETL 파이프라인 실행 (AuraDB 초기 적재)

백엔드 배포 후 AuraDB가 비어 있는 상태이므로 법령 데이터를 적재합니다.

```bash
# 로컬에서 AuraDB를 대상으로 실행
# .env의 NEO4J_URI를 AuraDB URI로 임시 교체 후 실행
NEO4J_URI="neo4j+s://<instance-id>.databases.neo4j.io" \
NEO4J_PASSWORD="<auradb-password>" \
python -m pipeline.scripts.initial_load
```

예상 소요 시간: 약 1~2시간 (법령 수, 네트워크 환경에 따라 변동)

---

## Phase 8: CORS 업데이트

Cloud Run 배포 + Firebase Hosting URL 확정 후 CORS 설정을 업데이트합니다.

```bash
gcloud run services update ordinance-backend \
  --region=asia-northeast3 \
  --update-env-vars="CORS_ORIGINS=https://ordinance-builder.web.app"
```

---

## 배포 후 검증 체크리스트

```bash
HOSTING_URL="https://ordinance-builder.web.app"

# 1. 백엔드 헬스 체크
curl "${BACKEND_URL}/docs"  # FastAPI Swagger UI 응답 확인

# 2. Firebase Hosting → Cloud Run 프록시 확인
curl "${HOSTING_URL}/api/v1/sessions" \
  -H "Authorization: Bearer <firebase-id-token>"
# 예상: 401 (토큰 없음) 또는 200 (토큰 있음)

# 3. Cloud SQL 연결 확인 (백엔드 로그)
gcloud logging read \
  'resource.type="cloud_run_revision" AND textPayload:"sessions table"' \
  --project=ordinance-builder \
  --limit=10

# 4. 세션 격리 확인
# 계정 A로 생성한 세션을 계정 B로 조회 → 403 응답 확인
```

---

## 비용 추정 (월간)

| 서비스 | 스펙 | 예상 비용 |
|--------|------|-----------|
| Cloud Run | CPU 2, RAM 2GB, min 1 인스턴스 | ~$20–35 |
| Cloud SQL | db-g1-small, 10GB SSD | ~$10 |
| Serverless VPC Connector | 2 인스턴스 | ~$5 |
| Neo4j AuraDB Professional | 1GB RAM | ~$65 |
| Firebase Hosting | 무료 tier | $0 |
| Secret Manager | ~10개 비밀 | ~$1 미만 |
| Artifact Registry | ~1GB | ~$1 미만 |
| Gemini / Claude / GPT-4o API | 세션당 $0.05–0.20 | 사용량 비례 |
| **합계 (API 제외)** | | **~$101–117/월** |

---

## 주요 결정 사항 기록

| 결정 | 내용 | 이유 |
|------|------|------|
| Cloud SQL Private IP | Public IP 미사용 | 보안 — 인터넷에서 직접 접근 불가 |
| Serverless VPC Connector | Cloud Run ↔ Cloud SQL 연결 | Private IP 접속을 위한 필수 구성 |
| Cloud Run ADC | `FIREBASE_CREDENTIALS_PATH` 미설정 | GCP 환경에서 서비스 계정 자동 인증 |
| Firebase Hosting 프록시 | `/api/**` → Cloud Run | 프론트엔드 코드에 백엔드 URL 하드코딩 불필요 |
| gunicorn -w 2 | 워커 2개 | Cloud Run CPU 2코어 기준, 메모리 2GB 제한 내 |
