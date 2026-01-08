import streamlit as st
import google.generativeai as genai
import sqlite3
import datetime
from gtts import gTTS
import io
import re

# --- KÜTÜPHANE KONTROLLERİ ---
try:
    import pypdf
    from docx import Document
    from PIL import Image
except ImportError:
    pass # Hata verirse sessizce devam et

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="auto" # Mobilde menü otomatik ayarlansın
)

# ============================================================
# 🚨 ACİL DURUM: TÜM GİZLİLİK AYARLARINI KALDIRDIM
# Menüler ve butonlar geri gelecek, böylece panel açılacak.
# ============================================================

# --- API ANAHTARI ---
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    API_KEY = "BURAYA_AIza_ILE_BASLAYAN_SIFRENI_YAPISTIR"

# --- YAPAY ZEKA BAĞLANTISI ---
try:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("models/gemini-pro")
except:
    pass # Hata olursa şimdilik geç

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

# --- ARAYÜZ (GİRİŞ EKRANI) ---
if not st.session_state.username:
    st.title("🎓 Okul Asistanı")
    isim = st.text_input("Adın nedir?")
    if st.button("Giriş Yap"):
        if isim:
            st.session_state.username = isim
            st.rerun()
    st.stop()

# --- ANA EKRAN VE SOL PANEL ---
username = st.session_state.username

# SOL PANEL (BURASI GERİ GELECEK)
with st.sidebar:
    st.title("⚙️ Menü")
    st.write(f"Hoş geldin, **{username}**!")
    st.divider()
    
    seviye = st.selectbox("Sınıfın:", ["İlkokul", "Ortaokul", "Lise", "Üniversite"])
    mod = st.selectbox("Mod Seç:", ["Sohbet", "Soru Çözümü", "Konu Anlatımı"])
    
    st.info("Panel artık görünüyor mu? 👀")
    
    if st.button("Çıkış Yap"):
        st.session_state.username = None
        st.rerun()

# SOHBET EKRANI
st.subheader(f"{mod} Modu - {seviye}")

# Geçmiş mesajlar
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Yeni mesaj
if prompt := st.chat_input("Mesaj yaz..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    
    # Cevap üret
    try:
        response = model.generate_content(prompt)
        cevap = response.text
    except:
        cevap = "Şu an bağlantıda bir sorun var veya API anahtarı eksik."
        
    st.session_state.messages.append({"role": "assistant", "content": cevap})
    with st.chat_message("assistant"):
        st.write(cevap)
