import streamlit as st
import google.generativeai as genai
import sqlite3
import datetime
from gtts import gTTS
import os
import io
import re

# --- KÜTÜPHANE KONTROLLERİ ---
try:
    import pypdf
    from docx import Document
    from PIL import Image
except ImportError:
    pass

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide"
)

# ============================================================
# 🛡️ TAM GİZLİLİK MODU (ARTIK GÜVENLE KULLANABİLİRİZ)
# ============================================================
st.markdown("""
<style>
    /* 1. TÜM ÜST MENÜYÜ, LOGOLARI VE BUTONLARI YOK ET */
    header {visibility: hidden !important; display: none !important;}
    [data-testid="stToolbar"] {visibility: hidden !important; display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}
    .stDeployButton {display: none !important;}
    
    /* 2. ALTTAKİ STREAMLIT YAZISINI YOK ET */
    footer {visibility: hidden !important; display: none !important;}
    
    /* 3. MOBİLDEKİ YAN MENÜYÜ TAMAMEN KAPAT (Kullanmayacağız) */
    [data-testid="stSidebar"] {display: none !important;}
    
    /* 4. SAYFAYI BİRAZ YUKARI ÇEK (Boşluk kalmasın) */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 5rem !important;
    }
    
    /* 5. GÖRÜNÜM AYARLARI */
    .premium-box {
        background: #1e293b;
        border: 1px solid #8b5cf6;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        margin-top: 10px;
    }
    .buy-btn {
        background: #8b5cf6;
        color: white !important;
        padding: 8px 15px;
        border-radius: 5px;
        text-decoration: none;
        display: block; 
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔒 API BAĞLANTISI
# ============================================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı eksik.")
    st.stop()

# --- YAPAY ZEKA ---
try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")
except:
    try: model = genai.GenerativeModel("gemini-pro")
    except: st.error("Model hatası."); st.stop()

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect('okul_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, credits INTEGER, last_login_date TEXT, is_premium INTEGER, premium_expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (username TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_codes (code TEXT PRIMARY KEY, is_used INTEGER, used_by TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- YARDIMCI FONKSİYONLAR ---
def get_user(conn, username): return conn.cursor().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
def create_user(conn, username): conn.cursor().execute("INSERT INTO users VALUES (?, 5, ?, 0, NULL)", (username, datetime.date.today().isoformat())); conn.commit()
def deduct_credit(conn, username): conn.cursor().execute("UPDATE users SET credits = credits - 1 WHERE username=?", (username,)); conn.commit()
def save_message(conn, username, role, content): conn.cursor().execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (username, role, content, datetime.datetime.now().isoformat())); conn.commit()
def get_history(conn, username): return conn.cursor().execute("SELECT role, content FROM messages WHERE username=? ORDER BY timestamp ASC", (username,)).fetchall()
def clean_text(text): return re.sub(r'^- ', '', text.replace("**", "").replace("*", "").replace("##", ""), flags=re.MULTILINE).strip()

def update_credits(conn, username):
    user = get_user(conn, username)
    if user:
        credits, last_date, is_prem, expiry = user[1], user[2], user[3], user[4]
        today = datetime.date.today().isoformat()
        if last_date != today:
            conn.cursor().execute("UPDATE users SET credits=?, last_login_date=? WHERE username=?", (5, today, username)); conn.commit(); credits=5
        return credits, is_prem, expiry
    return 0, 0, None

def activate_premium(conn, username, code):
    res = conn.cursor().execute("SELECT * FROM premium_codes WHERE code=?", (code,)).fetchone()
    if not res: return False, "❌ Geçersiz kod!"
    if res[1]: return False, "⚠️ Kod kullanılmış."
    exp = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    conn.cursor().execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE username=?", (exp, username))
    conn.cursor().execute("UPDATE premium_codes SET is_used=1, used_by=? WHERE code=?", (username, code))
    conn.commit(); return True, "✅ Premium Aktif!"

# --- UYGULAMA ---
if "messages" not in st.session_state: st.session_state.messages = []
if "username" not in st.session_state: st.session_state.username = None

# GİRİŞ EKRANI
if not st.session_state.username:
    st.markdown("<h1 style='text-align: center;'>🎓 Okul Asistanı</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username_input = st.text_input("Kullanıcı Adı", placeholder="Adın nedir?")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                if not get_user(conn, username_input): create_user(conn, username_input)
                st.session_state.username = username_input; st.rerun()
    st.stop()

# --- ANA EKRAN ---
username = st.session_state.username
kredi, is_premium, premium_expiry = update_credits(conn, username)
history = get_history(conn, username)

st.title("🎓 Okul Asistanı")

# ============================================================
# ⚙️ YENİ PANEL (Sidebar Yerine Expander)
# ============================================================
with st.expander(f"⚙️ AYARLAR & PANEL ({username}) - Tıkla Aç/Kapat", expanded=False):
    
    col_a, col_b = st.columns(2)
    with col_a:
        seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"])
        if is_premium: persona = st.selectbox("Öğretmen Tarzı", ["Normal", "Komik", "Disiplinli", "Samimi"])
        else: persona = "Normal"
        
    with col_b:
        mod = st.selectbox("Mod", ["Soru Çözümü", "Konu Anlatımı", "Kompozisyon", "Sohbet", "Ödev", "Dosya Analizi"])
        if is_premium: st.success(f"💎 Premium (Bitiş: {premium_expiry})")
        else: st.info(f"Kalan Hak: {kredi}/5")

    # Dosya Yükleme (Sadece buraya ekledik)
    uploaded_text, uploaded_image = "", None
    if "Dosya" in mod:
        if is_premium:
            f = st.file_uploader("📄 Dosya Yükle (PDF/Resim/Word)", type=['pdf','docx','txt','png','jpg'])
            if f:
                try:
                    if f.name.endswith(".pdf"): r = pypdf.PdfReader(f); uploaded_text="".join([p.extract_text() for p in r.pages]); st.success("PDF Hazır")
                    elif f.name.endswith(('.png','.jpg')): uploaded_image=Image.open(f); st.success("Resim Hazır")
                    elif f.name.endswith(".docx"): d=Document(f); uploaded_text="\n".join([p.text for p in d.paragraphs]); st.success("Word Hazır")
                except: st.error("Dosya okunamadı.")
        else: st.warning("Dosya analizi için Premium gerekli.")

    # Premium Satın Alma Kutusu
    if not is_premium:
        st.markdown("<div class='premium-box'>", unsafe_allow_html=True)
        col_p1, col_p2 = st.columns([2, 1])
        with col_p1:
            st.write("🚀 **Premium Ol** - 49 TL / 3 Ay")
            st.markdown('<a href="https://www.shopier.com/" target="_blank" class="buy-btn">SATIN AL</a>', unsafe_allow_html=True)
        with col_p2:
            kod = st.text_input("Kod:", placeholder="SOA-XXXX", label_visibility="collapsed")
            if st.button("Aktifleştir"):
                ok, msg = activate_premium(conn, username, kod.strip())
                if ok: st.balloons(); st.success(msg); st.rerun()
                else: st.error(msg)
        st.markdown("</div>", unsafe_allow_html=True)

    if st.button("Çıkış Yap", key="logout"):
        st.session_state.username = None; st.session_state.messages = []; st.rerun()

# ============================================================
# 💬 SOHBET ALANI
# ============================================================
for r, c in history:
    with st.chat_message(r): st.markdown(c)

if prompt := st.chat_input("Mesaj yaz..."):
    if kredi <= 0 and not is_premium: st.error("Günlük hakkın bitti.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                sys = f"Sen Okul Asistanısın. Seviye: {seviye}. Mod: {mod}. Stil: {persona}. Soru: {prompt}"
                con = [sys]
                if uploaded_text: con.append(f"Dosya: {uploaded_text}")
                if uploaded_image: con.append(uploaded_image)
                
                res = model.generate_content(con).text
                box.markdown(res)
                save_message(conn, username, "assistant", res)
                
                if not is_premium: deduct_credit(conn, username)
                if is_premium:
                    try:
                        tts = gTTS(clean_text(res), lang='tr')
                        aud = io.BytesIO(); tts.write_to_fp(aud)
                        st.audio(aud, format='audio/mp3')
                    except: pass
            except Exception as e: box.error(f"Hata: {e}")
