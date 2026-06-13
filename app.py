import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Page Config
st.set_page_config(
    page_title="AskFirst Health AI",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Premium CSS Styling for Rich Aesthetics
st.markdown("""
<style>
    /* Google Font Import */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Main Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #020617 100%);
        color: #f8fafc;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: rgba(15, 23, 42, 0.9) !important;
        backdrop-filter: blur(12px);
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Title and headers */
    h1, h2, h3 {
        background: linear-gradient(90deg, #38bdf8 0%, #818cf8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
    }
    
    /* Custom Chat Message Cards */
    .chat-bubble {
        padding: 16px 20px;
        border-radius: 16px;
        margin-bottom: 12px;
        max-width: 85%;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        line-height: 1.6;
    }
    
    .user-bubble {
        background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%);
        color: #f8fafc;
        margin-left: auto;
        border: 1px solid rgba(59, 130, 246, 0.2);
    }
    
    .assistant-bubble {
        background: rgba(30, 41, 59, 0.7);
        color: #f1f5f9;
        margin-right: auto;
        border: 1px solid rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(8px);
    }
    
    .avatar-label {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
        color: #94a3b8;
    }
    
    .user-avatar {
        color: #38bdf8;
        text-align: right;
    }
    
    .assistant-avatar {
        color: #818cf8;
    }
    
    /* Memory block design */
    .memory-card {
        background: rgba(129, 140, 248, 0.08);
        border: 1px dashed rgba(129, 140, 248, 0.3);
        border-radius: 12px;
        padding: 14px;
        font-size: 0.9rem;
        color: #c7d2fe;
        margin-top: 10px;
        margin-bottom: 10px;
        line-height: 1.5;
    }
    
    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #4f46e5 0%, #3730a3 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease-in-out !important;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.2) !important;
    }
    
    .stButton>button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 8px -1px rgba(79, 70, 229, 0.3) !important;
    }
    
    /* Text input background */
    div[data-baseweb="input"] {
        background-color: rgba(30, 41, 59, 0.5) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

# Helper functions to talk to backend
def fetch_threads():
    try:
        response = requests.get(f"{BACKEND_URL}/threads")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error connecting to backend: {e}")
    return []

def create_thread(title=None):
    try:
        payload = {"title": title} if title else {}
        response = requests.post(f"{BACKEND_URL}/threads", json=payload)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error creating thread: {e}")
    return None

def delete_thread(thread_id):
    try:
        response = requests.delete(f"{BACKEND_URL}/threads/{thread_id}")
        return response.status_code == 200
    except Exception as e:
        st.error(f"Error deleting thread: {e}")
    return False

def fetch_messages(thread_id):
    try:
        response = requests.get(f"{BACKEND_URL}/threads/{thread_id}/messages")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error fetching messages: {e}")
    return []

def send_message(thread_id, content):
    try:
        response = requests.post(
            f"{BACKEND_URL}/threads/{thread_id}/messages",
            json={"content": content}
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"Error sending message: {e}")
    return None

def fetch_memory():
    try:
        response = requests.get(f"{BACKEND_URL}/memory")
        if response.status_code == 200:
            return response.json().get("value", "")
    except Exception:
        pass
    return ""

def reset_memory():
    try:
        response = requests.post(f"{BACKEND_URL}/memory/reset")
        return response.status_code == 200
    except Exception:
        pass
    return False

# Initialize Session State
if "active_thread_id" not in st.session_state:
    st.session_state.active_thread_id = None

# App Layout
st.markdown("<h1>🩺 AskFirst Health Assistant</h1>", unsafe_allow_html=True)
st.markdown("<p style='color: #94a3b8; font-size: 1.1rem; margin-top: -10px;'>Your intelligent digital health companion with active universal memory</p>", unsafe_allow_html=True)

# SIDEBAR: Threads & Memory
with st.sidebar:
    st.markdown("### 💬 Conversations", unsafe_allow_html=True)
    
    # Button to start new thread
    if st.button("➕ New Conversation", use_container_width=True):
        new_t = create_thread()
        if new_t:
            st.session_state.active_thread_id = new_t["id"]
            st.rerun()

    # Load and display existing threads
    threads = fetch_threads()
    
    if threads:
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        for t in threads:
            col1, col2 = st.columns([0.85, 0.15])
            
            # Highlight active thread
            is_active = (t["id"] == st.session_state.active_thread_id)
            btn_label = f"📍 {t['title']}" if is_active else t['title']
            
            with col1:
                # Custom selection buttons
                if st.button(btn_label, key=f"select_{t['id']}", use_container_width=True):
                    st.session_state.active_thread_id = t["id"]
                    st.rerun()
            with col2:
                # Delete button
                if st.button("🗑️", key=f"del_{t['id']}", help="Delete thread"):
                    delete_thread(t["id"])
                    if st.session_state.active_thread_id == t["id"]:
                        st.session_state.active_thread_id = None
                    st.rerun()
    else:
        st.info("No active conversations. Start one above!")
        
    st.markdown("---")
    st.markdown("### 🧠 Universal Memory (AI Brain)", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #94a3b8;'>Things the AI remembers about you across all conversations:</p>", unsafe_allow_html=True)
    
    # Load and display memory profile
    memory_val = fetch_memory()
    
    st.markdown(f"<div class='memory-card'>{memory_val}</div>", unsafe_allow_html=True)
    
    if st.button("♻️ Reset AI Memory", use_container_width=True):
        if reset_memory():
            st.success("Memory cleared!")
            st.rerun()

# MAIN WINDOW: Chat Interface
if st.session_state.active_thread_id:
    # Find active thread info
    active_thread = next((t for t in threads if t["id"] == st.session_state.active_thread_id), None)
    thread_title = active_thread["title"] if active_thread else "Conversation"
    
    st.markdown(f"<h3>Current Session: {thread_title}</h3>", unsafe_allow_html=True)
    
    # Fetch and show messages
    messages = fetch_messages(st.session_state.active_thread_id)
    
    # Chat container
    chat_container = st.container()
    with chat_container:
        for msg in messages:
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="avatar-label user-avatar">You</div>
                <div class="chat-bubble user-bubble">{msg['content']}</div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="avatar-label assistant-avatar">AskFirst Assistant</div>
                <div class="chat-bubble assistant-bubble">{msg['content']}</div>
                """, unsafe_allow_html=True)
                
    # Spacing
    st.markdown("<div style='margin-top: 30px;'></div>", unsafe_allow_html=True)
    
    # Input Area (Sticky at the bottom)
    user_input = st.chat_input("Describe your symptoms or ask a health question...")
    if user_input:
        with st.spinner("Analyzing symptoms & retrieving medical context..."):
            send_message(st.session_state.active_thread_id, user_input)
        st.rerun()
else:
    # Welcome / Call to Action State
    st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.15, 0.7, 0.15])
    with col2:
        st.markdown("""
        <div style='background: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 20px; padding: 40px; text-align: center; backdrop-filter: blur(10px);'>
            <h2 style='margin-top: 0;'>Welcome to AskFirst Health Advisor</h2>
            <p style='color: #94a3b8; font-size: 1.1rem; line-height: 1.6;'>
                Describe your symptoms, log health conditions, or check risk factors. AskFirst uses an advanced memory loop that safely extracts key details about your physiology and medical history so you never have to repeat yourself in future conversations.
            </p>
            <div style='margin-top: 25px; font-weight: 500; color: #38bdf8;'>
                👈 Click "New Conversation" in the sidebar to begin.
            </div>
        </div>
        """, unsafe_allow_html=True)
