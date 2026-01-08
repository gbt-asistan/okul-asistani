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
    layout="wide",
    initial_sidebar_state="collapsed" # Telefondan girince menü kapalı başlar (Daha şık)
)

# ============================================================
# 🛡️ GÜVENLİ GİZLİLİK MODU (MOBİL UYUMLU)
# ============================================================
st.markdown("""
<style>
    /* 1. Sağ üstteki 'Deploy' butonunu YOK ET */
    .stDeployButton {display:none;}
    
    /* 2. Sağ üstteki 'Seçenekler' (Üç nokta ve GitHub simgesi) YOK ET */
    [data-testid="stToolbar"] {visibility: hidden !important;}
    
    /* 3. En tepedeki renkli çizgiyi YOK ET */
    [data-testid="stDecoration"] {display:none;}

    /* 4. En alttaki 'Made with Streamlit' yazısını YOK ET */
    footer {visibility: hidden;}
    
    /* 5. MENÜ BUTONU (SOL ÜST) İÇİN GÜVENLİK */
    /* Header'ı şeffaf yap ama içindeki menü butonunu (hamburger) gizleme */
    header {background: transparent !important;}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 🔑 API BAĞLANTISI
# ============================================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı bulunamadı. Ayarlar'dan (Secrets) ekleyiniz.")
    st.stop()

# --- YAPAY ZEKA (AKILLI MODEL SEÇİCİ - HATA VERMEZ) ---
try:
    genai.configure(api_key=API_KEY)
    
    # Varsayılan model
    secilen_model = "gemini-1.5-flash"
    
    # Eğer sunucuda bu yoksa, listedeki İLK çalışan modeli bul
    try:
        mevcut_modeller = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if mevcut_modeller:
            # Öncelik sırası: Flash -> Pro -> Herhangi biri
            if 'models/gemini-1.5-flash' in mevcut_modeller:
                secilen_model = 'models/gemini-1.5-flash'
            elif 'models/gemini-pro' in mevcut_modeller:
                secilen_model = 'models/gemini-pro'
            else:
                secilen_model = mevcut_modeller[0] # Ne varsa onu kullan
    except:
        pass # Listeleme hatası olursa varsayılanla devam et

    model = genai.GenerativeModel(secilen_model)
    
except Exception as e:
    st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- VERİTABANI ---
def init_db():
    conn = sqlite3.connect('okul_veritabani.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, credits INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (username TEXT, role TEXT, content TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- HAFIZA ---
if "messages" not in st.session_state: st.session_state.messages = []
if "username" not in st.session_state: st.session_state.username = None

# --- GİRİŞ EKRANI ---
if not st.session_state.username:
    st.markdown("<h1 style='text-align: center;'>🎓 Okul Asistanı</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username_input = st.text_input("Kullanıcı Adı", placeholder="Adın nedir?")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if username_input:
                st.session_state.username = username_input
                st.rerun()
    st.stop()

# --- ANA EKRAN ---
username = st.session_state.username

# CSS (Görünüm İyileştirme)
st.markdown("""
<style>
    .stChatInput textarea { height: 100px; }
</style>
""", unsafe_allow_html=True)

# SOL MENÜ
with st.sidebar:
    st.title("⚙️ Panel")
    st.write(f"👤 **{username}**")
    st.divider()
    
    seviye = st.selectbox("Sınıf", ["İlkokul", "Ortaokul", "Lise", "Üniversite"])
    mod = st.selectbox("Mod", ["Soru Çözümü", "Konu Anlatımı", "Kompozisyon", "Sohbet", "Ödev"])
    
    st.info("ℹ️ Sol üstteki ok/menü tuşu ile burayı kapatabilirsin.")
    
    if st.button("Çıkış Yap"):
        st.session_state.username = None
        st.session_state.messages = []
        st.rerun()

# SOHBET BAŞLIĞI
st.title("🎓 Okul Asistanı")
if "Kompozisyon" in mod: st.info("📝 Konuyu yaz, ben yazayım.")

# GEÇMİŞ MESAJLAR
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# MESAJ GİRİŞİ
if prompt := st.chat_input("Sorunu yaz..."):
    # Kullanıcı mesajı
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Yapay Zeka Cevabı
    with st.chat_message("assistant"):
        msg_box = st.empty()
        msg_box.markdown("Düşünüyorum... 🧠")
        
        try:
            # Prompt Hazırlığı
            system_prompt = f"""Sen Okul Asistanısın. 
            Seviye: {seviye}
            Mod: {mod}
            Soru/Mesaj: {prompt}"""
            
            response = model.generate_content(system_prompt)
            cevap = response.text
            
            msg_box.markdown(cevap)
            st.session_state.messages.append({"role": "assistant", "content": cevap})
            
            # Sesli Okuma (Opsiyonel - Hata verirse devam et)
            try:
                tts = gTTS(text=cevap.replace("*",""), lang='tr')
                aud = io.BytesIO(); tts.write_to_fp(aud)
                st.audio(aud, format='audio/mp3')
            except: pass

        except Exception as e:
            msg_box.error(f"Hata oluştu: {e}")
