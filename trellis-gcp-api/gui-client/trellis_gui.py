#!/usr/bin/env python3
"""
TRELLIS 3D Model Generation API - GUI Test Client

シンプルなStreamlitベースのGUIクライアントでTRELLIS APIをテストできます。
"""

import streamlit as st
import requests
import time
import json
import base64
from io import BytesIO
from PIL import Image
import os
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

# 設定
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
API_KEY = os.getenv("API_KEY", "dev-key-123456789")

class TrellisAPIClient:
    """TRELLIS API クライアント"""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })
    
    def health_check(self):
        """ヘルスチェック"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def generate_from_image(self, image_file, output_formats=["glb"], quality="balanced"):
        """画像から3Dモデル生成"""
        try:
            # 画像をBase64エンコード
            image_bytes = image_file.read()
            image_b64 = base64.b64encode(image_bytes).decode()
            
            payload = {
                "image_base64": image_b64,
                "output_formats": output_formats,
                "quality": quality
            }
            
            response = self.session.post(f"{self.base_url}/generate/image-to-3d", json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def generate_from_text(self, prompt, negative_prompt="", output_formats=["glb"], quality="balanced"):
        """テキストから3Dモデル生成"""
        try:
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "output_formats": output_formats,
                "quality": quality
            }
            
            response = self.session.post(f"{self.base_url}/generate/text-to-3d", json=payload)
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_job_status(self, job_id):
        """ジョブステータス取得"""
        try:
            response = self.session.get(f"{self.base_url}/jobs/{job_id}/status")
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_job_result(self, job_id):
        """ジョブ結果取得"""
        try:
            response = self.session.get(f"{self.base_url}/jobs/{job_id}/result")
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def list_jobs(self):
        """ジョブ一覧取得"""
        try:
            response = self.session.get(f"{self.base_url}/jobs")
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    def download_file(self, url):
        """ファイルをダウンロード"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            print(f"ダウンロードエラー: {str(e)}")
            return None
        except Exception as e:
            print(f"予期しないエラー: {str(e)}")
            return None


def main():
    st.set_page_config(
        page_title="TRELLIS 3D Model Generator",
        page_icon="🎨",
        layout="wide"
    )
    
    st.title("🎨 TRELLIS 3D Model Generator")
    st.markdown("**Microsoft TRELLIS を使用した3Dモデル生成API のテストクライアント**")
    
    # APIクライアント初期化
    client = TrellisAPIClient(API_BASE_URL, API_KEY)
    
    # サイドバー設定
    st.sidebar.header("⚙️ 設定")
    st.sidebar.text(f"API URL: {API_BASE_URL}")
    st.sidebar.text(f"API Key: {API_KEY[:16]}...")
    
    # ヘルスチェック
    if st.sidebar.button("🔍 ヘルスチェック"):
        with st.spinner("ヘルスチェック中..."):
            health = client.health_check()
            st.sidebar.json(health)
    
    # タブ作成
    tab1, tab2, tab3 = st.tabs(["📷 画像→3D", "✏️ テキスト→3D", "📋 ジョブ管理"])
    
    # 画像→3D タブ
    with tab1:
        st.header("📷 画像から3Dモデル生成")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "画像ファイルを選択",
                type=["jpg", "jpeg", "png", "bmp"],
                help="JPG, PNG, BMPファイルをアップロードしてください"
            )
            
            if uploaded_file:
                image = Image.open(uploaded_file)
                st.image(image, caption="アップロード画像", use_column_width=True)
        
        with col2:
            st.subheader("生成設定")
            output_formats = st.multiselect(
                "出力フォーマット",
                ["glb", "obj", "ply"],
                default=["glb"]
            )
            
            quality = st.selectbox(
                "品質設定",
                ["fast", "balanced", "high"],
                index=1
            )
            
            if st.button("🚀 3Dモデル生成開始", disabled=not uploaded_file):
                with st.spinner("生成リクエスト送信中..."):
                    result = client.generate_from_image(
                        uploaded_file, 
                        output_formats, 
                        quality
                    )
                    
                    if "error" in result:
                        st.error(f"エラー: {result['error']}")
                    else:
                        st.success("生成ジョブが開始されました！")
                        st.json(result)
                        
                        if "job_id" in result:
                            st.session_state.current_job_id = result["job_id"]
    
    # テキスト→3D タブ  
    with tab2:
        st.header("✏️ テキストから3Dモデル生成")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            prompt = st.text_area(
                "プロンプト（生成したいモデルの説明）",
                placeholder="例: A red sports car, highly detailed",
                height=100
            )
            
            negative_prompt = st.text_area(
                "ネガティブプロンプト（避けたい要素、任意）",
                placeholder="例: low quality, blurry, incomplete",
                height=60
            )
        
        with col2:
            st.subheader("生成設定")
            output_formats_text = st.multiselect(
                "出力フォーマット",
                ["glb", "obj", "ply"],
                default=["glb"],
                key="text_formats"
            )
            
            quality_text = st.selectbox(
                "品質設定",
                ["fast", "balanced", "high"],
                index=1,
                key="text_quality"
            )
            
            if st.button("🚀 3Dモデル生成開始", disabled=not prompt.strip(), key="text_generate"):
                with st.spinner("生成リクエスト送信中..."):
                    result = client.generate_from_text(
                        prompt, 
                        negative_prompt, 
                        output_formats_text, 
                        quality_text
                    )
                    
                    if "error" in result:
                        st.error(f"エラー: {result['error']}")
                    else:
                        job_id = result.get("job_id", "")
                        st.success("生成ジョブが開始されました！")
                        st.info(f"ジョブID: {job_id}")
                        st.session_state.current_job_id = job_id
                        
                        # 自動的に結果を待機・表示
                        with st.spinner("モデル生成中... (約15-20秒)"):
                            import time
                            time.sleep(15)  # 生成完了を待つ
                            
                        # 結果を自動取得・表示
                        result_data = client.get_job_result(job_id)
                        if "output_files" in result_data:
                            st.success("🎉 モデル生成完了！")
                            for i, file_info in enumerate(result_data["output_files"]):
                                st.markdown(f"**{file_info['format'].upper()}ファイル生成完了**")
                                st.markdown(f"- ファイル名: `{file_info['filename']}`")
                                st.markdown(f"- サイズ: {file_info['size_bytes']:,} bytes")
                                
                                # ダウンロードリンク
                                st.markdown(f"""
                                <a href="{file_info['url']}" 
                                   download="{file_info['filename']}"
                                   target="_blank"
                                   style="
                                       display: inline-block;
                                       background-color: #28a745;
                                       color: white;
                                       padding: 10px 20px;
                                       text-decoration: none;
                                       border-radius: 5px;
                                       font-weight: bold;
                                       margin: 5px 0;
                                   ">
                                   📥 {file_info['filename']} をダウンロード
                                </a>
                                """, unsafe_allow_html=True)
                                
                                # 直接ダウンロードボタンも追加
                                try:
                                    file_response = client.download_file(file_info['url'])
                                    if file_response:
                                        st.download_button(
                                            label=f"💾 {file_info['filename']} (直接ダウンロード)",
                                            data=file_response,
                                            file_name=file_info['filename'],
                                            mime="application/octet-stream"
                                        )
                                except Exception as e:
                                    st.text(f"直接ダウンロードエラー: {str(e)}")
                        else:
                            st.error("結果の取得に失敗しました")
    
    # ジョブ管理タブ
    with tab3:
        st.header("📋 ジョブ管理")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("ジョブステータス確認")
            
            # 現在のジョブIDがあれば表示
            if hasattr(st.session_state, 'current_job_id'):
                job_id = st.text_input(
                    "ジョブID", 
                    value=st.session_state.current_job_id
                )
            else:
                job_id = st.text_input("ジョブID")
            
            if st.button("📊 ステータス取得") and job_id:
                with st.spinner("ステータス取得中..."):
                    status = client.get_job_status(job_id)
                    
                    if "error" in status:
                        st.error(f"エラー: {status['error']}")
                    else:
                        st.json(status)
                        
                        # プログレスバー表示
                        if "progress" in status and status["progress"]:
                            st.progress(status["progress"])
            
            if st.button("📥 結果取得") and job_id:
                with st.spinner("結果取得中..."):
                    result = client.get_job_result(job_id)
                    
                    if "error" in result:
                        st.error(f"エラー: {result['error']}")
                    else:
                        st.json(result)
                        
                        # ダウンロードリンク表示
                        if "output_files" in result:
                            st.subheader("📁 生成ファイル")
                            for i, file_info in enumerate(result["output_files"]):
                                st.markdown(f"**{file_info['format'].upper()}ファイル:**")
                                
                                col_info, col_download = st.columns([2, 1])
                                
                                with col_info:
                                    st.markdown(f"- ファイル名: `{file_info['filename']}`")
                                    st.markdown(f"- サイズ: {file_info['size_bytes']:,} bytes")
                                    st.markdown(f"- フォーマット: {file_info['format'].upper()}")
                                
                                with col_download:
                                    # シンプルな直接ダウンロードリンク
                                    st.markdown(f"""
                                    <a href="{file_info['url']}" 
                                       download="{file_info['filename']}"
                                       target="_blank"
                                       style="
                                           display: inline-block;
                                           background-color: #28a745;
                                           color: white;
                                           padding: 10px 20px;
                                           text-decoration: none;
                                           border-radius: 5px;
                                           font-weight: bold;
                                           margin: 5px 0;
                                       ">
                                       📥 {file_info['filename']} をダウンロード
                                    </a>
                                    """, unsafe_allow_html=True)
                                    
                                    # Streamlit直接ダウンロードボタンも追加
                                    try:
                                        file_response = client.download_file(file_info['url'])
                                        if file_response:
                                            st.download_button(
                                                label=f"💾 {file_info['format'].upper()}",
                                                data=file_response,
                                                file_name=file_info['filename'],
                                                mime="application/octet-stream"
                                            )
                                    except Exception as e:
                                        st.text(f"エラー: {str(e)}")
                                    
                                    st.text(f"URL: {file_info['url']}")
                                
                                st.divider()
        
        with col2:
            st.subheader("ジョブ一覧")
            
            if st.button("🔄 一覧更新"):
                with st.spinner("ジョブ一覧取得中..."):
                    jobs = client.list_jobs()
                    
                    if "error" in jobs:
                        st.error(f"エラー: {jobs['error']}")
                    else:
                        if "jobs" in jobs and jobs["jobs"]:
                            for job in jobs["jobs"]:
                                job_status = job.get('status', 'unknown')
                                job_id = job.get('job_id', '')
                                
                                with st.expander(f"{job['job_type']} - {job_status} ({job_id[:8]}...)"):
                                    col_job_info, col_job_action = st.columns([2, 1])
                                    
                                    with col_job_info:
                                        st.json(job)
                                    
                                    with col_job_action:
                                        # 完了したジョブの場合、結果とダウンロード機能を提供
                                        if job_status == 'completed':
                                            if st.button(f"📥 結果取得", key=f"get_result_{job_id}"):
                                                with st.spinner("結果取得中..."):
                                                    job_result = client.get_job_result(job_id)
                                                    
                                                    if "error" not in job_result and "output_files" in job_result:
                                                        st.success("結果を取得しました！")
                                                        
                                                        # シンプル直接ダウンロードリンク（ジョブ一覧用）
                                                        for j, file_info in enumerate(job_result["output_files"]):
                                                            st.markdown(f"""<a href="{file_info['url']}" download="{file_info['filename']}" style="display: inline-block; background-color: #28a745; color: white; padding: 5px 10px; text-decoration: none; border-radius: 3px; margin: 2px;">💾 {file_info['format'].upper()}</a>""", unsafe_allow_html=True)
                                                    else:
                                                        st.error("結果の取得に失敗しました")
                                        
                                        elif job_status == 'processing':
                                            st.info("🔄 処理中...")
                                        elif job_status == 'failed':
                                            st.error("❌ 処理失敗")
                                        else:
                                            st.info(f"📋 ステータス: {job_status}")
                        else:
                            st.info("ジョブがありません")
    
    # 自動更新機能
    if hasattr(st.session_state, 'current_job_id'):
        if st.sidebar.checkbox("🔄 自動更新（5秒間隔）"):
            time.sleep(5)
            st.rerun()


if __name__ == "__main__":
    main()