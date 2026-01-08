import streamlit as st
import google.generativeai as genai
import sqlite3
import datetime
from gtts import gTTS
import os
import io
import re

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# ☢️ NÜKLEER GİZLİLİK MODU (CSS)
# ============================================================
st.markdown("""
    <style>
        /* 1. SAĞ ÜST MENÜ VE DEPLOY BUTONU (Kesin çözüm) */
        [data-testid="stToolbar"], 
        [data-testid="stHeader"], 
        .stDeployButton {
            visibility: hidden !important;
            display: none !important;
            height: 0px !important;
        }

        /* 2. HEADER GİZLENSİN AMA SOL ÜSTTEKİ OK TUŞU KALSIN */
        /* Header'ı görünmez yapıyoruz */
        header {
            background: transparent !important;
        }
        /* Ama sol menü açma butonunu (collapsedControl) zorla görünür yapıyoruz */
        [data-testid="collapsedControl"] {
            display: block !important;
            visibility: visible !important;
            top: 10px !important;
            left: 10px !important;
            z-index: 99999 !important; /* En üste çıkart */
        }

        /* 3. ALT BİLGİ VE LOGOLAR */
        footer {
            visibility: hidden !important;
            display: none !important;
        }
        #MainMenu {
            visibility: hidden !important;
            display: none !important;
        }
        
        /* 4. GÖRÜNÜM İYİLEŞTİRME */
        .block-container {
            padding-top: 20px !important; /* Üstteki boşluğu kapat */
        }
        
        /* Premium Kutusu Tasarımı */
        .premium-box {
            background: #1e293b; 
            border: 1px solid #8b5cf6; 
            padding: 15px; 
            border-radius: 10px; 
            text-align: center; 
            margin-bottom: 20px;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# ⚙️ GEREKLİ AYARLAR VE API
# ============================================================
try:
    import pypdf
    from docx import Document
    from PIL import Image
except ImportError:
    pass

if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı eksik.")
    st.stop()

try:
    genai.configure(api_key=API_KEY)
    calisan_model = "gemini-1.5-flash"
    try:
        models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if 'models/gemini-1.5-flash' in models: calisan_model = 'models/gemini-1.5-flash'
        elif 'models/gemini-pro' in models: calisan_model = 'models/gemini-pro'
    except: pass
    model = genai.GenerativeModel(calisan_model)
except Exception as e:
    st.error(f"Hata: {e}")
    st.stop()

# --- VERİTABANI VE FONKSİYONLAR ---
def init_db():
    conn = sqlite3.connect('okul_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, credits INTEGER, last_login_date TEXT, is_premium INTEGER, premium_expiry TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (username TEXT, role TEXT, content TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS premium_codes (code TEXT PRIMARY KEY, is_used INTEGER, used_by TEXT)''')
    conn.commit()
    return conn

conn = init_db()

def get_user(conn, username):
    return conn.cursor().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

def create_user(conn, username):
    conn.cursor().execute("INSERT INTO users VALUES (?, 5, ?, 0, NULL)", (username, datetime.date.today().isoformat()))
    conn.commit()

def update_credits(conn, username):
    c = conn.cursor()
    user = get_user(conn, username)
    if user:
        credits, last_date, is_premium, expiry = user[1], user[2], user[3], user[4]
        today = datetime.date.today().isoformat()
        if last_date != today:
            credits = 5
            c.execute("UPDATE users SET credits=?, last_login_date=? WHERE username=?", (5, today, username))
            conn.commit()
        if is_premium and expiry:
            if datetime.date.today() > datetime.date.fromisoformat(expiry):
                c.execute("UPDATE users SET is_premium=0, premium_expiry=NULL WHERE username=?", (username,))
                conn.commit()
                is_premium = 0
        return credits, is_premium, expiry
    return 0, 0, None

def deduct_credit(conn, username):
    conn.cursor().execute("UPDATE users SET credits = credits - 1 WHERE username=?", (username,))
    conn.commit()

def save_message(conn, username, role, content):
    conn.cursor().execute("INSERT INTO messages VALUES (?, ?, ?, ?)", (username, role, content, datetime.datetime.now().isoformat()))
    conn.commit()

def get_history(conn, username):
    return conn.cursor().execute("SELECT role, content FROM messages WHERE username=? ORDER BY timestamp ASC", (username,)).fetchall()

def activate_premium(conn, username, code):
    c = conn.cursor()
    res = c.execute("SELECT * FROM premium_codes WHERE code=?", (code,)).fetchone()
    if not res: return False, "❌ Geçersiz kod!"
    if res[1] == 1: return False, "⚠️ Kod kullanılmış."
    expiry = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    c.execute("UPDATE users SET is_premium=1, premium_expiry=? WHERE username=?", (expiry, username))
    c.execute("UPDATE premium_codes SET is_used=1, used_by=? WHERE code=?", (username, code))
    conn.commit()
    return True, "✅ Premium Aktif!"

def temizle_ve_konus(metin):
    return re.sub(r'^- ', '', metin.replace("**", "").replace("*", "").replace("##", "").replace("#", ""), flags=re.MULTILINE).strip()

# --- UYGULAMA MANTIĞI ---
if "messages" not in st.session_state: st.session_state.messages = []
if "username" not in st.session_state: st.session_state.username = None

# GİRİŞ EKRANI
if not st.session_state.username:
    st.markdown("<h1 style='text-align: center;'>🎓 Okul Asistanı Giriş</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username_input = st.text_input("Kullanıcı Adı", placeholder="Adın nedir?")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                user = get_user(conn, username_input)
                if not user: create_user(conn, username_input)
                st.session_state.username = username_input
                st.rerun()
            else: st.warning("İsim giriniz.")
    st.stop()

# ANA EKRAN
username = st.session_state.username
kredi, is_premium, premium_expiry = update_credits(conn, username)
history = get_history(conn, username)

# MENÜ
with st.sidebar:
    st.title("⚙️ Panel")
    if is_premium: st.success(f"💎 Premium\nBitiş: {premium_expiry}")
    else: 
        st.write(f"Hak: {kredi}/5")
        st.progress(kredi/5)
    st.divider()
    seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"])
    mod = st.selectbox("Mod", ["Soru Çözümü", "Konu Anlatımı", "Kompozisyon", "Sohbet", "Ödev", "Dosya Analizi"])
    
    st.subheader("Öğretmen Tarzı")
    if is_premium: persona = st.radio("Stil:", ["Normal", "Komik", "Disiplinli", "Samimi"])
    else: 
        st.info("🔒 Sadece Premium")
        persona = "Normal"
    
    st.divider()
    st.markdown("<div class='premium-box'>", unsafe_allow_html=True)
    if not is_premium:
        st.write("🚀 **Premium Ol**")
        st.write("Sınırsız Kullanım")
        st.markdown("<h2 style='color:white'>49 TL / 3 Ay</h2>", unsafe_allow_html=True)
        # BURAYA SHOPIER LINKINI EKLE:
        st.markdown('<a href="https://www.shopier.com/" target="_blank" style="background:#8b5cf6;color:white;padding:8px 15px;border-radius:5px;text-decoration:none;display:block;">SATIN AL</a>', unsafe_allow_html=True)
        kod = st.text_input("Kod:", placeholder="SOA-XXXX")
        if st.button("Aktifleştir"):
            ok, msg = activate_premium(conn, username, kod.strip())
            if ok: st.balloons(); st.success(msg); st.rerun()
            else: st.error(msg)
    else: st.write("Keyfini Çıkar! 🎉")
    st.markdown("</div>", unsafe_allow_html=True)
    
    if st.button("Çıkış Yap"):
        st.session_state.username = None; st.session_state.messages = []; st.rerun()

# SOHBET
st.title("🎓 Okul Asistanı")
if "Kompozisyon" in mod: st.info("📝 Konuyu yazman yeterli.")

uploaded_text = ""
uploaded_image = None
if "Dosya" in mod:
    if is_premium:
        f = st.file_uploader("Dosya", type=['pdf','docx','txt','png','jpg'])
        if f:
            try:
                if f.name.endswith(".pdf"): r = pypdf.PdfReader(f); uploaded_text = "".join([p.extract_text() for p in r.pages]); st.success("PDF Tamam!")
                elif f.name.endswith(('.png','.jpg')): uploaded_image = Image.open(f); st.image(uploaded_image, width=200); st.success("Resim Tamam!")
                elif f.name.endswith(".docx"): d = Document(f); uploaded_text = "\n".join([p.text for p in d.paragraphs]); st.success("Word Tamam!")
                elif f.name.endswith(".txt"): uploaded_text = str(f.read(),"utf-8"); st.success("Metin Tamam!")
            except: st.error("Dosya okunamadı.")
    else: st.warning("🔒 Dosya için Premium gerekli.")

for r, c in history:
    with st.chat_message(r): st.markdown(c)
if not history:
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Mesaj..."):
    if kredi <= 0 and not is_premium: st.error("Günlük hak bitti. Premium al.")
    else:
        save_message(conn, username, "user", prompt)
        st.session_state.messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.markdown(prompt)

        with st.chat_message("assistant"):
            box = st.empty(); box.markdown("...")
            try:
                sys = f"Sen Okul Asistanısın. Seviye: {seviye}. Mod: {mod}. Tarz: {persona}. Soru: {prompt}"
                con = [sys]
                if uploaded_text: con.append(f"Dosya: {uploaded_text}")
                if uploaded_image: con.append(uploaded_image)
                
                res = model.generate_content(con).text
                box.markdown(res)
                save_message(conn, username, "assistant", res)
                
                if not is_premium: deduct_credit(conn, username)
                if is_premium:
                    try:
                        tts = gTTS(temizle_ve_konus(res), lang='tr')
                        aud = io.BytesIO(); tts.write_to_fp(aud)
                        st.audio(aud, format='audio/mp3')
                    except: pass
            except Exception as e: box.error(f"Hata: {e}")
