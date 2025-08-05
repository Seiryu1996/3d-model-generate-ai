# TRELLIS 3D Model Generation API

Microsoft TRELLISを使用した3Dモデル生成REST APIシステムです。画像やテキストプロンプトから高品質な3Dモデルを生成できます。

![TRELLIS API Architecture](https://img.shields.io/badge/Architecture-Microservices-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-red)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)
![GCP](https://img.shields.io/badge/GCP-Ready-orange)

## 🎯 主な機能

- 🖼️ **画像→3D変換**: 画像ファイルから3Dモデル生成
- ✏️ **テキスト→3D変換**: テキストプロンプトから3Dモデル生成
- 🔄 **非同期処理**: ジョブキューによる効率的な処理管理
- 📊 **リアルタイム監視**: 生成進捗のリアルタイムトラッキング  
- 🎛️ **品質制御**: Fast/Balanced/High の3段階品質設定
- 📁 **多形式対応**: GLB, OBJ, PLY形式での出力
- 🔐 **セキュア**: APIキー認証・レート制限
- ☁️ **クラウド対応**: GCP本格デプロイ対応

## 🏗️ システムアーキテクチャ

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client App    │───▶│   FastAPI       │───▶│  TRELLIS        │
│   (GUI/API)     │    │   (REST API)    │    │  (GPU Worker)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │  Job Queue      │    │  3D Models      │
                       │  (Redis/Tasks)  │    │  (Storage)      │
                       └─────────────────┘    └─────────────────┘
```

## 🚀 クイックスタート

### 前提条件

- Docker & Docker Compose
- 16GB以上のGPUメモリ（推奨）
- Python 3.10+

### 1. リポジトリクローン

```bash
git clone <repository-url>
cd trellis-gcp-api
```

### 2. 環境設定

```bash
# 環境変数設定
cp .env.example .env
# 必要に応じて.envファイルを編集

# Secret Key生成
export SECRET_KEY=$(openssl rand -base64 32)
```

### 3. 開発環境起動

```bash
# Docker Compose でサービス起動
docker compose up -d

# ログ確認
docker compose logs -f api
```

### 4. 動作確認

```bash
# ヘルスチェック
curl http://localhost:8000/api/v1/health

# API仕様確認
open http://localhost:8000/docs
```

## 🖥️ GUIテストクライアント

StreamlitベースのGUIクライアントでAPIを簡単にテストできます。

```bash
cd gui-client

# 依存関係インストール
pip install -r requirements.txt

# 環境設定
cp .env.example .env

# GUI起動
streamlit run trellis_gui.py
```

ブラウザで `http://localhost:8501` にアクセスしてGUIを使用できます。

## 📖 API使用方法

### 認証

全APIエンドポイントは認証が必要です：

```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/health
```

開発環境では `dev-key-123456789` が使用可能です。

### 画像から3D生成

```bash
curl -X POST http://localhost:8000/api/v1/generate/image-to-3d \
  -H "Authorization: Bearer dev-key-123456789" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/car.jpg",
    "output_formats": ["glb"],
    "quality": "balanced"
  }'
```

### テキストから3D生成

```bash
curl -X POST http://localhost:8000/api/v1/generate/text-to-3d \
  -H "Authorization: Bearer dev-key-123456789" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A red sports car, highly detailed",
    "output_formats": ["glb"],
    "quality": "high"
  }'
```

### ジョブステータス確認

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}/status \
  -H "Authorization: Bearer dev-key-123456789"
```

詳細な使用方法は [API使用方法ドキュメント](docs/API_USAGE.md) を参照してください。

## ☁️ 本番デプロイ

### GCP本格デプロイ

Google Cloud Platformへの本格デプロイ手順は [GCPデプロイ手順書](docs/GCP_DEPLOYMENT.md) を参照してください。

主な構成要素：
- **Compute Engine**: API・WorkerのVMインスタンス
- **Cloud Storage**: 3Dモデルファイル保存
- **Firestore**: ジョブ管理データベース  
- **Cloud Tasks**: 非同期ジョブキュー
- **Cloud Load Balancer**: 負荷分散・SSL終端

## 🔧 開発環境

### ディレクトリ構造

```
trellis-gcp-api/
├── src/                    # ソースコード
│   ├── api/               # FastAPI アプリケーション
│   ├── models/            # データモデル
│   ├── services/          # ビジネスロジック
│   ├── repositories/      # データアクセス層
│   └── utils/            # ユーティリティ
├── docker/               # Docker設定
├── gui-client/           # Streamlit GUIクライアント
├── docs/                 # ドキュメント
└── tests/               # テストコード
```

### 開発用コマンド

```bash
# API開発サーバー起動
docker compose up api

# ワーカー単体起動  
docker compose up worker

# 全サービス再起動
docker compose restart

# ログ監視
docker compose logs -f api worker

# データベースリセット
docker compose down -v
```

## ⚡ パフォーマンス

### 品質設定と処理時間

| 品質 | 処理時間 | 推論ステップ | 用途 |
|------|----------|-------------|------|
| Fast | 3-5分 | 20 | プロトタイプ・確認用 |
| Balanced | 10-15分 | 50 | 一般的な用途 |
| High | 25-45分 | 100 | 最終製品・商用利用 |

## 🔒 セキュリティ

### 認証・認可

- APIキーベース認証
- ユーザー別アクセス制御
- レート制限（デフォルト: 10req/min）

### セキュリティヘッダー

自動適用されるセキュリティヘッダー：
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (本番のみ)

## 🆘 サポート

### ドキュメント

- [API使用方法](docs/API_USAGE.md)
- [GCPデプロイ手順](docs/GCP_DEPLOYMENT.md)
- [GUIクライアント使用方法](gui-client/README.md)

### トラブルシューティング

よくある問題と解決方法：

**Q: GPUが認識されない**
```bash
# NVIDIA-Docker設定確認
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi
```

**Q: メモリ不足エラー**
```bash
# GPU メモリ確認
docker compose exec worker nvidia-smi
```

**Q: 認証エラー**
```bash
# APIキー確認
curl -H "Authorization: Bearer dev-key-123456789" http://localhost:8000/api/v1/health
```

## 📄 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) ファイルを参照

## 🤝 コントリビューション

1. Forkしてfeatureブランチ作成
2. 変更をコミット
3. テスト実行・パス確認
4. Pull Request作成

---

**🎨 TRELLIS 3D Model Generation API - 画像・テキストから高品質3Dモデルを生成** 

Built with ❤️ using Microsoft TRELLIS, FastAPI, and Google Cloud Platform