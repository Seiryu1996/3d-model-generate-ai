# TRELLIS API GUIクライアント

TRELLIS 3D Model Generation APIをテストするためのシンプルなStreamlitベースのGUIアプリケーションです。

## 機能

- 🖼️ **画像から3Dモデル生成**: 画像ファイルをアップロードして3Dモデルを生成
- ✏️ **テキストから3Dモデル生成**: テキストプロンプトから3Dモデルを生成  
- 📊 **ジョブ管理**: 生成ジョブのステータス確認、結果取得、一覧表示
- ⚙️ **リアルタイム監視**: 自動更新機能でジョブの進行状況をリアルタイム監視

## セットアップ

### 1. 依存関係インストール

```bash
cd gui-client
pip install -r requirements.txt
```

### 2. 環境設定

```bash
cp .env.example .env
```

`.env`ファイルを編集してAPI URLとAPIキーを設定：

```bash
# ローカル開発環境
API_BASE_URL=http://localhost:8000/api/v1
API_KEY=dev-key-123456789

# 本番環境
# API_BASE_URL=https://your-api-domain.com/api/v1
# API_KEY=your-actual-api-key
```

### 3. アプリケーション起動

```bash
streamlit run trellis_gui.py
```

ブラウザで `http://localhost:8501` にアクセスしてGUIを使用できます。

## 使用方法

### 画像から3Dモデル生成

1. **画像→3D**タブを選択
2. 画像ファイル（JPG, PNG, BMP）をアップロード
3. 出力フォーマット（GLB, OBJ, PLY）を選択
4. 品質設定（Fast, Balanced, High）を選択
5. **3Dモデル生成開始**ボタンをクリック

### テキストから3Dモデル生成

1. **テキスト→3D**タブを選択
2. プロンプトを入力（例: "A red sports car, highly detailed"）
3. ネガティブプロンプトを入力（任意）
4. 出力フォーマットと品質設定を選択
5. **3Dモデル生成開始**ボタンをクリック

### ジョブ管理

1. **ジョブ管理**タブを選択
2. ジョブIDを入力して**ステータス取得**で進行状況確認
3. **結果取得**で完了したジョブのファイルを取得
4. **一覧更新**で全ジョブの一覧を表示

## 注意事項

- APIサーバーが起動している必要があります
- 有効なAPIキーが必要です
- 大きな画像ファイルは処理に時間がかかる場合があります
- 生成にはGPUが推奨されます（CPUでも動作しますが非常に遅くなります）

## トラブルシューティング

### 接続エラー
```
ConnectionError: HTTPSConnectionPool...
```
- API URLが正しいか確認
- APIサーバーが起動しているか確認

### 認証エラー
```
{"detail":"API key required"}
```
- `.env`ファイルのAPI_KEYが正しいか確認
- APIキーが有効期限内か確認

### タイムアウトエラー
- ネットワーク接続を確認
- APIサーバーの負荷状況を確認