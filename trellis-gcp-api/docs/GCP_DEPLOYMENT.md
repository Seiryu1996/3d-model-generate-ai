# TRELLIS API GCPデプロイ手順書

## 概要

TRELLIS 3D Model Generation APIをGoogle Cloud Platform (GCP)に本格デプロイする手順です。
GPU対応のCompute Engine、Cloud Storage、Firestore、Cloud Tasksを使用した本番環境構築を説明します。

## 前提条件

- GCPアカウントと有効な請求アカウント
- Google Cloud SDK (`gcloud`) のインストール
- Docker と Docker Compose のインストール
- 十分なGCPクォータ（特にGPU）

## アーキテクチャ

```
Internet → Cloud Load Balancer → API (Compute Engine)
                                  ↓
                               Worker (GPU VM)
                                  ↓
Storage ← Cloud Storage    Firestore → Cloud Tasks
```

## 1. GCPプロジェクト設定

### 1.1 プロジェクト作成と初期設定

```bash
# プロジェクト作成
export PROJECT_ID="trellis-api-production"
gcloud projects create $PROJECT_ID

# プロジェクト設定
gcloud config set project $PROJECT_ID

# 請求アカウント設定（必要に応じて）
gcloud billing accounts list
gcloud billing projects link $PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### 1.2 必要なAPIの有効化

```bash
# 必要なGoogle Cloud APIを有効化
gcloud services enable compute.googleapis.com
gcloud services enable container.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable firestore.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable monitoring.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

## 2. ストレージ設定

### 2.1 Cloud Storageバケット作成

```bash
# 環境変数設定
export REGION="us-central1"  # GPUが利用可能なリージョン
export BUCKET_PREFIX="trellis-api-prod"

# バケット作成
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${BUCKET_PREFIX}-models
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${BUCKET_PREFIX}-input
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${BUCKET_PREFIX}-output
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${BUCKET_PREFIX}-temp

# バケットの公開アクセス無効化
gsutil iam ch allUsers:objectViewer gs://${BUCKET_PREFIX}-output  # 出力のみ読み取り可能
```

### 2.2 Firestore設定

```bash
# Firestoreデータベース作成（ネイティブモード）
gcloud firestore databases create --region=$REGION

# インデックス作成（必要に応じて）  
gcloud firestore indexes composite create --collection-group=jobs \
  --field-config field-path=user_id,order=ascending \
  --field-config field-path=created_at,order=descending
```

### 2.3 Cloud Tasks設定

```bash
# キュー作成
gcloud tasks queues create trellis-tasks --location=$REGION

# キュー設定
gcloud tasks queues update trellis-tasks --location=$REGION \
  --max-concurrent-dispatches=10 \
  --max-dispatches-per-second=5
```

## 3. コンテナイメージのビルドとデプロイ

### 3.1 Artifact Registry設定

```bash
# リポジトリ作成
gcloud artifacts repositories create trellis-api \
  --repository-format=docker \
  --location=$REGION

# Docker認証設定
gcloud auth configure-docker ${REGION}-docker.pkg.dev
```

### 3.2 イメージビルド

```bash
# プロジェクトルートディレクトリで実行
cd trellis-gcp-api

# APIイメージビルド
docker build -f docker/Dockerfile.api \
  -t ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:latest .

# Workerイメージビルド
docker build -f docker/Dockerfile.worker \
  -t ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:latest .

# イメージプッシュ
docker push ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:latest
docker push ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:latest
```

### 3.3 Cloud Build設定（オプション）

```yaml
# cloudbuild.yaml
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'docker/Dockerfile.api', '-t', '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:$SHORT_SHA', '.']
  
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'docker/Dockerfile.worker', '-t', '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:$SHORT_SHA', '.']
  
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:$SHORT_SHA']
  
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:$SHORT_SHA']

substitutions:
  _REGION: us-central1

images:
  - '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:$SHORT_SHA'
  - '${_REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:$SHORT_SHA'
```

## 4. Compute Engine設定

### 4.1 APIサーバー用VM作成

```bash
# サービスアカウント作成
gcloud iam service-accounts create trellis-api-sa \
  --display-name="TRELLIS API Service Account"

# 必要な権限付与
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-api-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-api-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-api-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"

# APIサーバーVM作成
gcloud compute instances create trellis-api-server \
  --zone=${REGION}-a \
  --machine-type=e2-standard-4 \
  --service-account=trellis-api-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --boot-disk-size=50GB \
  --tags=http-server,https-server \
  --metadata-from-file startup-script=startup-api.sh
```

### 4.2 GPU Worker用VM作成

```bash
# GPU対応サービスアカウント作成
gcloud iam service-accounts create trellis-worker-sa \
  --display-name="TRELLIS Worker Service Account"

# GPU Worker権限付与
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-worker-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-worker-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:trellis-worker-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.taskRunner"

# GPU Worker VM作成（T4 GPU使用）
gcloud compute instances create trellis-gpu-worker \
  --zone=${REGION}-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --service-account=trellis-worker-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --boot-disk-size=100GB \
  --maintenance-policy=TERMINATE \
  --metadata-from-file startup-script=startup-worker.sh
```

## 5. 起動スクリプト作成

### 5.1 APIサーバー起動スクリプト

```bash
# startup-api.sh
cat > startup-api.sh << 'EOF'
#!/bin/bash

# Docker設定
docker-credential-gcr configure-docker

# 環境変数設定
export PROJECT_ID=$(curl -s "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google")
export REGION="us-central1"

# APIコンテナ実行
docker run -d --name trellis-api \
  --restart unless-stopped \
  -p 8000:8000 \
  -e GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
  -e GCS_BUCKET_MODELS="trellis-api-prod-models" \
  -e GCS_BUCKET_INPUT="trellis-api-prod-input" \
  -e GCS_BUCKET_OUTPUT="trellis-api-prod-output" \
  -e GCS_BUCKET_TEMP="trellis-api-prod-temp" \
  -e FIRESTORE_COLLECTION_JOBS="jobs" \
  -e CLOUD_TASKS_QUEUE="trellis-tasks" \
  -e CLOUD_TASKS_LOCATION=$REGION \
  -e SECRET_KEY="$(openssl rand -base64 32)" \
  -e DEBUG="false" \
  ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/api:latest

# ヘルスチェック設定
while ! curl -f http://localhost:8000/api/v1/health; do
  echo "Waiting for API to start..."
  sleep 5
done

echo "TRELLIS API started successfully"
EOF
```

### 5.2 GPU Worker起動スクリプト

```bash
# startup-worker.sh
cat > startup-worker.sh << 'EOF'
#!/bin/bash

# NVIDIA GPU ドライバーインストール
/opt/deeplearning/install-driver.sh

# Docker設定
docker-credential-gcr configure-docker

# 環境変数設定
export PROJECT_ID=$(curl -s "http://metadata.google.internal/computeMetadata/v1/project/project-id" -H "Metadata-Flavor: Google")
export REGION="us-central1"

# GPU Worker コンテナ実行
docker run -d --name trellis-worker \
  --restart unless-stopped \
  --runtime=nvidia \
  --gpus all \
  -e GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
  -e GCS_BUCKET_MODELS="trellis-api-prod-models" \
  -e GCS_BUCKET_INPUT="trellis-api-prod-input" \
  -e GCS_BUCKET_OUTPUT="trellis-api-prod-output" \
  -e GCS_BUCKET_TEMP="trellis-api-prod-temp" \
  -e FIRESTORE_COLLECTION_JOBS="jobs" \
  -e CLOUD_TASKS_QUEUE="trellis-tasks" \
  -e CLOUD_TASKS_LOCATION=$REGION \
  -e CUDA_VISIBLE_DEVICES=0 \
  ${REGION}-docker.pkg.dev/$PROJECT_ID/trellis-api/worker:latest

echo "TRELLIS GPU Worker started successfully"
EOF
```

## 6. ネットワーク設定

### 6.1 ファイアウォールルール

```bash
# HTTPSトラフィック許可
gcloud compute firewall-rules create allow-trellis-api \
  --allow tcp:8000 \
  --source-ranges 0.0.0.0/0 \
  --target-tags http-server

# ヘルスチェック用
gcloud compute firewall-rules create allow-health-check \
  --allow tcp:8000 \
  --source-ranges 130.211.0.0/22,35.191.0.0/16 \
  --target-tags http-server
```

### 6.2 ロードバランサー設定

```bash
# インスタンスグループ作成
gcloud compute instance-groups unmanaged create trellis-api-group \
  --zone=${REGION}-a

gcloud compute instance-groups unmanaged add-instances trellis-api-group \
  --zone=${REGION}-a \
  --instances=trellis-api-server

# ヘルスチェック作成
gcloud compute health-checks create http trellis-api-health-check \
  --port 8000 \
  --request-path /api/v1/health

# バックエンドサービス作成
gcloud compute backend-services create trellis-api-backend \
  --protocol HTTP \
  --health-checks trellis-api-health-check \
  --global

gcloud compute backend-services add-backend trellis-api-backend \
  --instance-group trellis-api-group \
  --instance-group-zone ${REGION}-a \
  --global

# URLマップ作成
gcloud compute url-maps create trellis-api-url-map \
  --default-service trellis-api-backend

# HTTPSプロキシ作成（SSL証明書は別途取得）
gcloud compute target-https-proxies create trellis-api-https-proxy \
  --url-map trellis-api-url-map \
  --ssl-certificates your-ssl-cert

# グローバル転送ルール作成
gcloud compute forwarding-rules create trellis-api-forwarding-rule \
  --global \
  --target-https-proxy trellis-api-https-proxy \
  --ports 443
```

## 7. SSL証明書設定

### 7.1 管理されたSSL証明書（推奨）

```bash
# 管理されたSSL証明書作成
gcloud compute ssl-certificates create trellis-api-ssl-cert \
  --domains your-api-domain.com \
  --global

# HTTPSプロキシに適用
gcloud compute target-https-proxies update trellis-api-https-proxy \
  --ssl-certificates trellis-api-ssl-cert
```

### 7.2 Let's Encrypt（代替方法）

```bash
# Certbot使用してSSL証明書取得
# VMにSSHアクセスして実行
sudo apt update
sudo apt install certbot
sudo certbot certonly --standalone -d your-api-domain.com

# 証明書をGCPにアップロード
gcloud compute ssl-certificates create trellis-api-ssl-cert \
  --certificate=/etc/letsencrypt/live/your-api-domain.com/fullchain.pem \
  --private-key=/etc/letsencrypt/live/your-api-domain.com/privkey.pem \
  --global
```

## 8. 監視・ログ設定

### 8.1 Cloud Monitoring設定

```bash
# アラートポリシー作成（例：レスポンス時間監視）
gcloud alpha monitoring policies create --policy-from-file=monitoring-policy.yaml
```

```yaml
# monitoring-policy.yaml
displayName: "TRELLIS API Response Time Alert"
conditions:
  - displayName: "API Response Time > 30s"
    conditionThreshold:
      filter: 'resource.type="gce_instance" AND resource.label.instance_name="trellis-api-server"'
      comparison: COMPARISON_GREATER_THAN
      thresholdValue: 30000
      duration: 300s
notificationChannels:
  - projects/$PROJECT_ID/notificationChannels/YOUR_NOTIFICATION_CHANNEL
```

### 8.2 ログ設定

```bash
# カスタムログベースアラート作成
gcloud logging sinks create trellis-api-errors \
  bigquery.googleapis.com/projects/$PROJECT_ID/datasets/api_logs \
  --log-filter='resource.type="gce_instance" AND severity>=ERROR'
```

## 9. セキュリティ設定

### 9.1 Cloud Armor設定

```bash
# セキュリティポリシー作成
gcloud compute security-policies create trellis-api-security-policy

# レート制限ルール追加
gcloud compute security-policies rules create 1000 \
  --security-policy trellis-api-security-policy \
  --expression "true" \
  --action "rate-based-ban" \
  --rate-limit-threshold-count=100 \
  --rate-limit-threshold-interval-sec=60 \
  --ban-duration-sec=600

# バックエンドサービスに適用
gcloud compute backend-services update trellis-api-backend \
  --security-policy trellis-api-security-policy \
  --global
```

### 9.2 IAMロール最小権限化

```bash
# カスタムロール作成
gcloud iam roles create trellisApiRole \
  --project=$PROJECT_ID \
  --title="TRELLIS API Role" \
  --description="Minimal permissions for TRELLIS API" \
  --permissions=storage.objects.create,storage.objects.delete,storage.objects.get,storage.objects.list,datastore.entities.create,datastore.entities.get,datastore.entities.update,cloudtasks.tasks.create
```

## 10. デプロイ確認

### 10.1 動作確認

```bash
# API エンドポイント確認取得
export API_URL=$(gcloud compute forwarding-rules describe trellis-api-forwarding-rule --global --format="value(IPAddress)")

# ヘルスチェック
curl https://$API_URL/api/v1/health

# 認証テスト
curl -H "Authorization: Bearer your-api-key" \
  https://$API_URL/api/v1/jobs
```

### 10.2 負荷テスト

```bash
# Apache Bench使用例
ab -n 100 -c 10 -H "Authorization: Bearer your-api-key" \
  https://your-api-domain.com/api/v1/health
```

## 11. 運用・メンテナンス

### 11.1 自動スケーリング設定

```bash
# インスタンステンプレート作成
gcloud compute instance-templates create trellis-api-template \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --machine-type=e2-standard-4 \
  --service-account=trellis-api-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform \
  --metadata-from-file startup-script=startup-api.sh

# マネージドインスタンスグループ作成
gcloud compute instance-groups managed create trellis-api-mig \
  --template=trellis-api-template \
  --size=2 \
  --zone=${REGION}-a

# オートスケーラー設定
gcloud compute instance-groups managed set-autoscaling trellis-api-mig \
  --zone=${REGION}-a \
  --max-num-replicas=10 \
  --min-num-replicas=2 \
  --target-cpu-utilization=0.7
```

### 11.2 バックアップ設定

```bash
# Firestoreエクスポート設定
gcloud scheduler jobs create app-engine backup-firestore \
  --schedule="0 2 * * *" \
  --timezone="Asia/Tokyo" \
  --http-method=POST \
  --uri="https://firestore.googleapis.com/v1/projects/$PROJECT_ID/databases/(default):exportDocuments" \
  --headers="Authorization=Bearer $(gcloud auth print-access-token)" \
  --message-body='{"outputUriPrefix":"gs://trellis-api-prod-backup/firestore"}'
```

### 11.3 更新デプロイ

```bash
# ローリングアップデート
gcloud compute instance-groups managed rolling-action start-update trellis-api-mig \
  --version=template=trellis-api-template-v2 \
  --zone=${REGION}-a
```

## 12. 費用最適化

### 12.1 プリエンプティブルインスタンス使用

```bash
# Workerにプリエンプティブルインスタンス使用
gcloud compute instances create trellis-gpu-worker-preemptible \
  --preemptible \
  --zone=${REGION}-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  # ... 他のオプション
```

### 12.2 スケジュールベースの起動停止

```bash
# Cloud Scheduler使用してWorkerの起動停止制御
gcloud scheduler jobs create compute start-worker \
  --schedule="0 9 * * 1-5" \
  --timezone="Asia/Tokyo" \
  --target-type=compute \
  --target-compute-service=compute.googleapis.com \
  --target-compute-method=POST \
  --target-compute-uri="/compute/v1/projects/$PROJECT_ID/zones/${REGION}-a/instances/trellis-gpu-worker/start"
```

## トラブルシューティング

### よくある問題

1. **GPU クォータ不足**
   ```bash
   gcloud compute project-info describe --project=$PROJECT_ID
   # QuotasセクションでGPU使用量確認
   ```

2. **メモリ不足**
   ```bash
   # VM監視
   gcloud compute instances get-serial-port-output trellis-gpu-worker --zone=${REGION}-a
   ```

3. **ストレージアクセス権限**
   ```bash
   # サービスアカウント権限確認 
   gcloud projects get-iam-policy $PROJECT_ID
   ```

この手順に従ってGCPに本格デプロイを行うことで、スケーラブルで高可用性なTRELLIS API環境を構築できます。