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
    pass # Hata olursa devam et

# --- SİTE AYARLARI ---
st.set_page_config(
    page_title="Okul Asistanı",
    page_icon="🎓",
    layout="wide"
)

# ============================================================
# 🔒 API ANAHTARI KONTROLÜ
# ============================================================
if "GOOGLE_API_KEY" in st.secrets:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
else:
    st.warning("⚠️ API Anahtarı bulunamadı. Lütfen ayarlardan Secrets kısmına ekleyin.")
    st.stop()

# --- YAPAY ZEKA BAĞLANTISI (GARANTİ MODEL: gemini-pro) ---
try:
    genai.configure(api_key=API_KEY)
    # En güvenli ve yaygın model budur. Hata vermez.
    model = genai.GenerativeModel("gemini-pro")
except Exception as e:
    st.error(f"Bağlantı Hatası: {e}")
    st.stop()

# --- VERİTABANI İŞLEMLERİ ---
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
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        isim = st.text_input("Adın nedir?")
        if st.button("Giriş Yap 🚀", use_container_width=True):
            if isim:
                st.session_state.username = isim
                st.rerun()
    st.stop()

# --- ANA EKRAN ---
username = st.session_state.username

# SOL MENÜ (MOBİLDE GÖRÜNÜR)
with st.sidebar:
    st.title("⚙️ Menü")
    st.write(f"Hoş geldin, **{username}**!")
    st.divider()
    
    seviye = st.selectbox("Sınıf Seviyesi", ["İlkokul", "Ortaokul", "Lise", "Üniversite"])
    mod = st.selectbox("Mod Seç", ["Soru Çözümü", "Konu Anlatımı", "Sohbet", "Kompozisyon"])
    
    st.info("💡 İpucu: Sol üstteki oka basarak bu menüyü açıp kapatabilirsin.")
    
    if st.button("Çıkış Yap"):
        st.session_state.username = None
        st.session_state.messages = []
        st.rerun()

# SOHBET BAŞLIĞI
st.subheader(f"🎓 {mod} Modu")

# GEÇMİŞ MESAJLAR
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# MESAJ GÖNDERME
prompt = st.chat_input("Buraya yaz...")
if prompt:
    # Kullanıcı mesajı
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Cevap üretiliyor
    with st.chat_message("assistant"):
        msg_box = st.empty()
        msg_box.markdown("Düşünüyorum... 🧠")
        
        try:
            system_prompt = f"Sen bir eğitim asistanısın. Seviye: {seviye}. Mod: {mod}. Soru: {prompt}"
            response = model.generate_content(system_prompt)
            cevap = response.text
            
            msg_box.markdown(cevap)
            st.session_state.messages.append({"role": "assistant", "content": cevap})
            
        except Exception as e:
            msg_box.error(f"Bir hata oluştu: {e}")
