import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, date
import pytz
from fpdf import FPDF
from PIL import Image
import os
import tempfile
import plotly.express as px

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="MiniVagon Bulut", page_icon="☁️", layout="wide")

# --- SABİTLER ---
SHEET_ADI = "MiniVagonDB"
RESIM_KLASORU = "resimler"

# --- ZAMAN AYARI ---
def simdi():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

# --- GOOGLE SHEETS BAĞLANTISI ---
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_sheet():
    client = get_client()
    return client.open(SHEET_ADI)

# --- AKILLI PARA VE SAYI ÇEVİRİCİ ---
def safe_float(val):
    """Her türlü para formatını (51.805,20 veya 1250.50) float sayıya çevirir."""
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        if isinstance(val, (int, float)): return float(val)
        
        s = str(val).replace("TL", "").replace("tl", "").replace("₺", "").replace(" ", "").strip()
        
        if "." in s and "," in s:
            if s.rfind(",") > s.rfind("."): # 1.250,50 (TR)
                s = s.replace(".", "").replace(",", ".")
            else: # 1,250.50 (EN)
                s = s.replace(",", "")
        elif "," in s: # 1250,50
            s = s.replace(",", ".")
            
        return float(s)
    except:
        return 0.0

def format_excel_tl(val):
    """Sayıyı Excel'in ve sizin istediğiniz 51.805,20 metin formatına çevirir."""
    try:
        # Önce standart 1,250.50 yapıp sonra noktalarla virgülleri takas ediyoruz
        s = "{:,.2f}".format(float(val))
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

# --- VERİ İŞLEMLERİ ---
@st.cache_data(ttl=5)
def verileri_getir(sayfa_adi):
    sh = get_sheet()
    try:
        w = sh.worksheet(sayfa_adi)
        return w.get_all_records()
    except:
        return []

def cache_temizle():
    st.cache_data.clear()

# --- MENÜ ---
menu_options = ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"]
menu = st.sidebar.radio("Menü", menu_options)

# Ürün ve Maliyet Fonksiyonları (GUNCEL_URUNLER yüklemesi için yukarıda)
def get_urun_resimleri():
    sabitler = {"SATRANÇ": "satranc.jpg", "6 LI KADEHLİK": "6likadehlik.jpg"} # Örnek
    db = verileri_getir("Urunler")
    for u in db:
        if isinstance(u, dict) and "Urun Adi" in u: sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

GUNCEL_URUNLER = get_urun_resimleri()

# --------------------------------------------------------------------------------
# 6. CARİ HESAPLAR (DÜZELTİLMİŞ KAYIT SİSTEMİ)
# --------------------------------------------------------------------------------
if menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    
    with st.expander("➕ Yeni Fatura / Ödeme İşle", expanded=True):
        with st.form("cari_form_yeni"):
            c1, c2 = st.columns(2)
            m_data = verileri_getir("Cariler")
            c_list = list(set([r['Cari Adı'] for r in m_data])) if m_data else []
            
            cari_secim = c1.selectbox("Cari Hesap:", ["Yeni Ekle..."] + c_list)
            if cari_secim == "Yeni Ekle...": ad = c1.text_input("Cari Adı Girin:")
            else: ad = cari_secim
            
            f_tarih = c2.date_input("Fatura/İşlem Tarihi")
            f_no = c1.text_input("Fatura/Fiş No")
            not_ac = st.text_input("Açıklama/Not")
            
            t_inp = st.text_input("Tutar (Örn: 51.805,20)")
            
            # Algılama Kontrolü (Görsel Geri Bildirim)
            if t_inp:
                algilanan = safe_float(t_inp)
                st.info(f"Sistem şunu kaydedecek: **{format_excel_tl(algilanan)} TL**")
            
            tip = st.radio("İşlem Türü:", ["Fatura Girişi (BORÇ)", "Ödeme Yapıldı (ALACAK)"], horizontal=True)
            
            if st.form_submit_button("KAYDET"):
                if ad and t_inp:
                    val = safe_float(t_inp)
                    # Excel'e metin olarak tam formatlı gönderiyoruz
                    excel_formatli_tutar = format_excel_tl(val)
                    tarih_s = f_tarih.strftime("%d.%m.%Y")
                    tip_s = "BORÇ" if "BORÇ" in tip else "ALACAK"
                    
                    sh = get_sheet()
                    ws = sh.worksheet("Cariler")
                    # Sütunlar: Cari Adı, Tarih, Fatura No, Not, Tutar, Tip
                    ws.append_row([ad, tarih_s, f_no, not_ac, excel_formatli_tutar, tip_s])
                    
                    st.success(f"Başarıyla Kaydedildi: {excel_formatli_tutar} TL")
                    cache_temizle()
                    st.rerun()

    if m_data:
        df_cari = pd.DataFrame(m_data)
        secili_c = st.selectbox("Hesap Detayı:", df_cari['Cari Adı'].unique())
        if secili_c:
            sub = df_cari[df_cari['Cari Adı'] == secili_c].copy()
            
            # Görüntüleme ve Hesaplama için sayıya çevir
            sub['T_Sayi'] = sub['Tutar'].apply(safe_float)
            
            st.table(sub[["Tarih", "Fatura No", "Not", "Tutar", "Tip"]])
            
            borc = sub[sub['Tip'] == "BORÇ"]['T_Sayi'].sum()
            alacak = sub[sub['Tip'] == "ALACAK"]['T_Sayi'].sum()
            bakiye = alacak - borc
            
            k1, k2, k3 = st.columns(3)
            k1.metric("Toplam Borç", format_excel_tl(borc))
            k2.metric("Toplam Ödeme", format_excel_tl(alacak))
            color = "normal" if bakiye >= 0 else "inverse"
            k3.metric("GÜNCEL BAKİYE", format_excel_tl(bakiye), delta_color=color)

# Diğer menüler v65'teki gibi çalışmaya devam eder (Hata almamak için v65'in kalanını buraya eklemeyi unutmayın)
# ... (Kodun geri kalanı v65 ile aynıdır, sadece Cari kısmındaki append_row ve formatlama değişti)
