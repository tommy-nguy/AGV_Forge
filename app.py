import streamlit as st
import subprocess
import threading
import time
import json
from pathlib import Path
import sys

# Thêm thư mục gốc vào sys.path để import các module cần cho UI (không dùng trong thread)
sys.path.insert(0, str(Path(__file__).parent))

from forge_core.config import get_config
from forge_jobs.channel_manager import ChannelManager
from forge_jobs.job_manager import JobManager

st.set_page_config(page_title="AGV Forge", layout="wide")
st.title("🎬 AGV Forge - Automated Video Factory")

# Khởi tạo managers
config = get_config()
channel_mgr = ChannelManager(config.database_path)
job_mgr = JobManager(config.database_path, channel_mgr)

# -------------------- Hàm chạy job qua subprocess --------------------
def run_job_subprocess(job_id: str, skip_review: bool = True):
    """Gọi CLI để chạy job trong tiến trình riêng."""
    cmd = [
        sys.executable,  # Dùng chính Python hiện tại
        "cli.py",
        "job", "run",
        job_id,
        "--skip-review" if skip_review else ""
    ]
    cmd = [arg for arg in cmd if arg]  # Loại bỏ chuỗi rỗng
    try:
        # Chạy subprocess, không cần capture output để tránh treo
        subprocess.Popen(cmd, cwd=Path(__file__).parent)
        st.session_state.job_status[job_id] = "✅ Đã khởi động (đang chạy nền)"
    except Exception as e:
        st.session_state.job_status[job_id] = f"❌ Lỗi khởi động: {str(e)}"

# -------------------- Giao diện chính --------------------
if "job_status" not in st.session_state:
    st.session_state.job_status = {}

# Sidebar: Chọn channel
st.sidebar.header("1. Chọn Channel")
channels = channel_mgr.list_channels(include_inactive=False)
if channels:
    channel_options = {ch.channel_id: ch.channel_name for ch in channels}
    selected_channel_id = st.sidebar.selectbox(
        "Channel",
        options=list(channel_options.keys()),
        format_func=lambda x: f"{channel_options[x]} ({x})"
    )
else:
    st.sidebar.warning("Chưa có channel nào. Hãy tạo channel bằng CLI.")
    selected_channel_id = None

# Main area
st.header("2. Tạo Job Mới")
uploaded_file = st.file_uploader("Chọn video", type=["mp4", "mov", "avi"])
brief = st.text_area("Brief (mô tả nội dung mong muốn)", placeholder="Video 30 giây về...")

if st.button("🚀 Tạo và Chạy Job", type="primary", disabled=not selected_channel_id):
    if uploaded_file is None or not brief:
        st.error("Vui lòng upload video và nhập brief.")
    else:
        # Lưu file upload
        temp_dir = Path("/tmp/agv_forge_uploads")
        temp_dir.mkdir(exist_ok=True)
        video_path = temp_dir / uploaded_file.name
        with open(video_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        # Tạo job
        with st.spinner("Đang tạo job..."):
            record = job_mgr.create_job(
                channel_id=selected_channel_id,
                input_assets=[str(video_path)],
                metadata={"brief": brief}
            )
            st.success(f"Job created: {record.job_id}")
            
            # Chạy job qua subprocess
            run_job_subprocess(record.job_id, skip_review=True)
            st.info(f"Job {record.job_id} đã được gửi đi. Xem tiến độ trong bảng bên dưới (cần refresh).")

# Danh sách job
st.header("📋 Danh sách Job")
if selected_channel_id:
    jobs = job_mgr.list_jobs(selected_channel_id)
    if jobs:
        job_data = []
        for j in jobs:
            # Lấy trạng thái mới nhất từ DB
            try:
                fresh = job_mgr.get_job(j.job_id)
                state = fresh.current_state
                progress = fresh.progress_percent
            except:
                state = j.current_state
                progress = j.progress_percent
            
            # Kết hợp với session state (nếu có thông báo lỗi khởi động)
            display_state = st.session_state.job_status.get(j.job_id, state)
            job_data.append({
                "Job ID": j.job_id,
                "Trạng thái": display_state,
                "Tiến độ": f"{progress}%",
                "Cập nhật": j.updated_at[:16]
            })
        st.dataframe(job_data, use_container_width=True)
        if st.button("🔄 Refresh"):
            st.rerun()
    else:
        st.info("Chưa có job nào.")
else:
    st.info("Vui lòng chọn channel.")