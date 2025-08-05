# TRELLIS 3D Model Generation API 使用方法

## 概要

TRELLIS 3D Model Generation APIは、Microsoft TRELLISを使用して画像やテキストから3Dモデルを生成するREST APIです。

## 認証

全てのAPIエンドポイントは認証が必要です。APIキーをAuthorizationヘッダーまたはX-API-Keyヘッダーで送信してください。

```bash
# Authorizationヘッダー使用
curl -H "Authorization: Bearer YOUR_API_KEY" ...

# X-API-Keyヘッダー使用  
curl -H "X-API-Key: YOUR_API_KEY" ...
```

## ベースURL

- **開発環境**: `http://localhost:8000/api/v1`
- **本番環境**: `https://your-api-domain.com/api/v1`

## エンドポイント一覧

### 1. ヘルスチェック

APIの稼働状況を確認します。

```bash
GET /health
```

**レスポンス例:**
```json
{
  "success": true,
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "version": "1.0.0",
  "services": {
    "api": "healthy",
    "storage": "healthy"
  }
}
```

### 2. 画像から3Dモデル生成

画像ファイルから3Dモデルを生成します。

```bash
POST /generate/image-to-3d
```

**リクエストボディ:**
```json
{
  "image_url": "https://example.com/image.jpg",  // 画像URLまたは
  "image_base64": "iVBORw0KGgoAAAANSUhEUgAA...",   // Base64エンコード画像
  "output_formats": ["glb", "obj"],              // 出力フォーマット
  "quality": "balanced"                          // 品質設定
}
```

**パラメータ:**
- `image_url` (string, optional): 画像のURL
- `image_base64` (string, optional): Base64エンコードされた画像データ
- `output_formats` (array): 出力フォーマット `["glb", "obj", "ply"]`
- `quality` (string): 品質設定 `"fast"`, `"balanced"`, `"high"`

**curl例:**
```bash
curl -X POST "http://localhost:8000/api/v1/generate/image-to-3d" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "image_url": "https://example.com/car.jpg",
    "output_formats": ["glb"],
    "quality": "balanced"
  }'
```

**レスポンス例:**
```json
{
  "success": true,
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "pending",
  "estimated_completion_time": "2024-01-01T12:15:00Z"
}
```

### 3. テキストから3Dモデル生成

テキストプロンプトから3Dモデルを生成します。

```bash
POST /generate/text-to-3d
```

**リクエストボディ:**
```json
{
  "prompt": "A red sports car, highly detailed",
  "negative_prompt": "low quality, blurry",
  "output_formats": ["glb", "obj"],
  "quality": "balanced"
}
```

**パラメータ:**
- `prompt` (string, required): 生成したいモデルの説明（最大1000文字）
- `negative_prompt` (string, optional): 避けたい要素（最大500文字）
- `output_formats` (array): 出力フォーマット
- `quality` (string): 品質設定

**curl例:**
```bash
curl -X POST "http://localhost:8000/api/v1/generate/text-to-3d" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A red sports car, highly detailed",
    "output_formats": ["glb"],
    "quality": "high"
  }'
```

### 4. ジョブステータス確認

生成ジョブの進行状況を確認します。

```bash
GET /jobs/{job_id}/status
```

**curl例:**
```bash
curl "http://localhost:8000/api/v1/jobs/123e4567-e89b-12d3-a456-426614174000/status" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**レスポンス例:**
```json
{
  "success": true,
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "job_type": "image-to-3d",
  "status": "processing",
  "progress": 0.65,
  "created_at": "2024-01-01T12:00:00Z",
  "updated_at": "2024-01-01T12:10:00Z",
  "started_at": "2024-01-01T12:05:00Z",
  "completed_at": null,
  "processing_time_seconds": null,
  "error_message": null
}
```

**ステータス一覧:**
- `pending`: 待機中
- `processing`: 処理中
- `completed`: 完了
- `failed`: 失敗
- `cancelled`: キャンセル

### 5. ジョブ結果取得

完了したジョブの結果を取得します。

```bash
GET /jobs/{job_id}/result
```

**curl例:**
```bash
curl "http://localhost:8000/api/v1/jobs/123e4567-e89b-12d3-a456-426614174000/result" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**レスポンス例:**
```json
{
  "success": true,
  "job_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "completed",
  "output_files": [
    {
      "format": "glb",
      "url": "https://storage.googleapis.com/bucket/output.glb",
      "size_bytes": 1024000,
      "filename": "model.glb"
    }
  ],
  "processing_time_seconds": 45.5,
  "error_message": null
}
```

### 6. ジョブ一覧取得

ユーザーのジョブ一覧を取得します。

```bash
GET /jobs?page=1&page_size=10&status_filter=completed
```

**クエリパラメータ:**
- `page` (int): ページ番号（デフォルト: 1）
- `page_size` (int): 1ページあたりの件数（デフォルト: 10、最大: 100）
- `status_filter` (string, optional): ステータスフィルター

**curl例:**
```bash
curl "http://localhost:8000/api/v1/jobs?page=1&page_size=5" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 7. ジョブ削除

ジョブをキャンセル/削除します。

```bash
DELETE /jobs/{job_id}
```

**curl例:**
```bash
curl -X DELETE "http://localhost:8000/api/v1/jobs/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## レート制限

- デフォルト: 1分間に10リクエスト
- 制限に達すると HTTP 429 (Too Many Requests) が返されます
- レスポンスヘッダーで制限情報を確認できます：
  - `X-RateLimit-Limit`: 制限値
  - `X-RateLimit-Reset`: リセット時刻

## エラーレスポンス

APIエラーは以下の形式で返されます：

```json
{
  "success": false,
  "error": "Error message",
  "detail": "Detailed error description"
}
```

**主なHTTPステータスコード:**
- `200 OK`: 成功
- `202 Accepted`: ジョブ受付完了
- `400 Bad Request`: 不正なリクエスト
- `401 Unauthorized`: 認証エラー
- `403 Forbidden`: アクセス拒否
- `404 Not Found`: リソースが見つからない
- `429 Too Many Requests`: レート制限超過
- `500 Internal Server Error`: サーバーエラー

## 品質設定詳細

### Fast (高速)
- 処理時間: 3-5分
- 推論ステップ: 20
- 品質: 基本的
- 用途: プロトタイプ、確認用

### Balanced (バランス)
- 処理時間: 10-15分  
- 推論ステップ: 50
- 品質: 中程度
- 用途: 一般的な用途

### High (高品質)
- 処理時間: 25-45分
- 推論ステップ: 100
- 品質: 高品質
- 用途: 最終製品、商用利用

## 出力フォーマット詳細

### GLB (GL Transmission Format Binary)
- 用途: Web表示、AR/VR
- 特徴: テクスチャ、アニメーション対応
- サイズ: 中程度

### OBJ (Wavefront OBJ)
- 用途: 3Dソフトウェア汎用
- 特徴: 広く対応、シンプル
- サイズ: 小さい

### PLY (Polygon File Format)
- 用途: 学術研究、点群データ
- 特徴: 頂点データ重視
- サイズ: 小さい

## 使用例（Python）

```python
import requests
import time

# API設定
API_BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "your-api-key"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# テキストから3D生成
def generate_3d_from_text(prompt):
    payload = {
        "prompt": prompt,
        "output_formats": ["glb"],
        "quality": "balanced"
    }
    
    response = requests.post(
        f"{API_BASE_URL}/generate/text-to-3d",
        json=payload,
        headers=headers
    )
    
    if response.status_code == 202:
        job_data = response.json()
        job_id = job_data["job_id"]
        print(f"ジョブ開始: {job_id}")
        
        # ステータス監視
        while True:
            status_response = requests.get(
                f"{API_BASE_URL}/jobs/{job_id}/status",
                headers=headers
            )
            
            status_data = status_response.json()
            print(f"ステータス: {status_data['status']}")
            
            if status_data["status"] == "completed":
                # 結果取得
                result_response = requests.get(
                    f"{API_BASE_URL}/jobs/{job_id}/result",
                    headers=headers
                )
                result_data = result_response.json()
                
                for file_info in result_data["output_files"]:
                    print(f"ファイル: {file_info['url']}")
                break
            elif status_data["status"] == "failed":
                print(f"エラー: {status_data['error_message']}")
                break
                
            time.sleep(10)  # 10秒待機
    else:
        print(f"エラー: {response.text}")

# 実行例
generate_3d_from_text("A red sports car")
```

## 注意事項

1. **GPU推奨**: TRELLISはGPU処理が前提です。CPUでは非常に時間がかかります。
2. **メモリ要件**: 16GB以上のGPUメモリが推奨されます。
3. **処理時間**: 品質設定によって大幅に変わります。
4. **ファイルサイズ**: 画像は100MB以下を推奨します。
5. **同時処理**: デフォルトでは1ジョブずつ処理されます。