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

def safe_int(val):
    return int(safe_float(val))

def format_excel_tl(val):
    """Sayıyı Excel'in ve sizin istediğiniz 51.805,20 metin formatına çevirir."""
    try:
        s = "{:,.2f}".format(float(val))
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

# --- VERİ İŞLEMLERİ (CACHING) ---
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

# --- SİSTEM KAYIT FONKSİYONLARI ---
def siparis_ekle(satir):
    sh = get_sheet()
    ws = sh.worksheet("Siparisler")
    ws.append_row(satir)
    cache_temizle()

def cari_islem_ekle(satir):
    sh = get_sheet()
    ws = sh.worksheet("Cariler")
    ws.append_row(satir)
    cache_temizle()

def yeni_urun_resim_ekle(ad, resim_adi):
    sh = get_sheet()
    ws = sh.worksheet("Urunler")
    ws.append_row([ad, resim_adi])
    cache_temizle()

# --- TEDARİK VE CARİ ENTEGRASYONU ---
def tedarik_durumunu_guncelle_ve_cariye_isle(siparis_bilgileri, cari_hesap, maliyet_sozlugu):
    sh = get_sheet()
    ws_siparis = sh.worksheet("Siparisler")
    ws_cari = sh.worksheet("Cariler")
    tarih_str = simdi().strftime("%d.%m.%Y")
    
    try:
        headers = ws_siparis.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        tedarik_col = headers.index("Tedarik Durumu") + 1

        toplam_net_maliyet = 0
        islenen_nolar = []

        for sip in siparis_bilgileri:
            sip_no = sip['Siparis No']
            u1, a1 = sip.get('Ürün 1', ''), safe_int(sip.get('Adet 1', 0))
            u2, a2 = sip.get('Ürün 2', ''), safe_int(sip.get('Adet 2', 0))
            toplam_net_maliyet += (maliyet_sozlugu.get(u1, 0) * a1) + (maliyet_sozlugu.get(u2, 0) * a2)
            islenen_nolar.append(str(sip_no))
            cell = ws_siparis.find(str(sip_no), in_column=sip_no_col)
            if cell: ws_siparis.update_cell(cell.row, tedarik_col, "TEDARİKÇİ KESTİ")

        tutar_kdv_dahil = toplam_net_maliyet * 1.20
        excel_tutar = format_excel_tl(tutar_kdv_dahil)
        aciklama = f"Sipariş Maliyetleri: {', '.join(islenen_nolar)}"
        
        ws_cari.append_row([cari_hesap, tarih_str, "OTO-ALIS", aciklama, excel_tutar, "BORÇ"])
        cache_temizle()
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

# --- YARDIMCI VERİ ÇEKİCİLER ---
def get_urun_resimleri():
    sabitler = {"Örnek Ürün": "logo.png"}
    db = verileri_getir("Urunler")
    for u in db:
        if isinstance(u, dict) and "Urun Adi" in u: sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

def get_maliyet_dict():
    db = verileri_getir("Maliyetler")
    m_dict = {}
    for m in db:
        u_id = m.get("Ürün Id") or m.get("Urun Id")
        cost = safe_float(m.get("MALİYET") or m.get("Maliyet"))
        if u_id: m_dict[u_id] = cost
    return m_dict

GUNCEL_URUNLER = get_urun_resimleri()

# --- MENÜ SİSTEMİ ---
menu = st.sidebar.radio("Menü", ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"])

# 1. SİPARİŞ GİRİŞİ
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        u1 = st.selectbox("1. Ürün Seçimi", list(GUNCEL_URUNLER.keys()))
        a1 = st.number_input("1. Ürün Adet", 1, 100, 1)
        st.markdown("---")
        ikinci = st.checkbox("2. Ürün Ekle (+)")
        u2, a2 = "", ""
        if ikinci:
            u2 = st.selectbox("2. Ürün Seçimi", list(GUNCEL_URUNLER.keys()), key="u2_s")
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_n")
    with col2:
        with st.form("siparis_form"):
            t_inp = st.text_input("Sipariş Tutarı (Örn: 51.805,20)")
            if t_inp: st.caption(f"Algılanan: {format_excel_tl(safe_float(t_inp))} TL")
            odeme = st.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            adres = st.text_area("Adres")
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"
            if st.form_submit_button("KAYDET"):
                mevcut = verileri_getir("Siparisler")
                y_no = 1000
                if mevcut: y_no = int(pd.to_numeric(pd.DataFrame(mevcut)['Siparis No'], errors='coerce').max()) + 1
                tutar_f = format_excel_tl(safe_float(t_inp))
                satir = [y_no, simdi().strftime("%d.%m.%Y %H:%M"), "YENİ SİPARİŞ", ad, tel, "", "", u1, a1, "", u2, a2, "", tutar_f, odeme, "Whatsapp", adres, "", fatura, "BEKLİYOR"]
                siparis_ekle(satir)
                st.success("Kaydedildi!")

# 4. ALIŞ VE TEDARİK
elif menu == "🧾 Alış ve Tedarik":
    st.header("Tedarikçi Alış Yönetimi")
    c_data = verileri_getir("Cariler")
    c_list = list(set([r['Cari Adı'] for r in c_data])) if c_data else []
    m_dict = get_maliyet_dict()
    s_data = verileri_getir("Siparisler")
    if s_data:
        df_s = pd.DataFrame(s_data)
        bekleyenler = df_s[df_s["Tedarik Durumu"] != "TEDARİKÇİ KESTİ"].copy()
        if not bekleyenler.empty:
            secilen_cari = st.selectbox("Tedarikçi Seç:", c_list)
            st.dataframe(bekleyenler[["Siparis No", "Müşteri", "Ürün 1", "Adet 1"]])
            secenekler = bekleyenler.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']}", axis=1).tolist()
            sel = st.multiselect("Faturası Gelen Siparişleri Seç:", secenekler)
            if st.button("ONAYLA VE CARİYE İŞLE"):
                ids = [int(s.split(" - ")[0]) for s in sel]
                islenecek = bekleyenler[bekleyenler['Siparis No'].isin(ids)].to_dict('records')
                res = tedarik_durumunu_guncelle_ve_cariye_isle(islenecek, secilen_cari, m_dict)
                if res == "BAŞARILI": st.success("İşlendi!"); st.rerun()
        else: st.success("Bekleyen tedarik yok.")

# 6. CARİ HESAPLAR
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Hesap Takip Defteri")
    
    with st.expander("➕ Yeni İşlem Kaydet (Fatura/Ödeme)", expanded=True):
        with st.form("cari_form_yeni"):
            c1, c2 = st.columns(2)
            m_data = verileri_getir("Cariler")
            c_list = list(set([r['Cari Adı'] for r in m_data])) if m_data else []
            ad_sec = c1.selectbox("Cari Hesap:", ["Yeni Ekle..."] + c_list)
            if ad_sec == "Yeni Ekle...": ad = c1.text_input("Yeni Cari Adı:")
            else: ad = ad_sec
            
            f_no = c2.text_input("Fatura No")
            t_inp = st.text_input("Tutar (Örn: 51.805,20)")
            if t_inp: st.info(f"Sistem: **{format_excel_tl(safe_float(t_inp))} TL** kaydedecek.")
            
            tip = st.radio("İşlem:", ["Fatura Girişi (BORÇ)", "Ödeme Yapıldı (ALACAK)"], horizontal=True)
            if st.form_submit_button("KAYDET"):
                t_excel = format_excel_tl(safe_float(t_inp))
                cari_islem_ekle([ad, simdi().strftime("%d.%m.%Y"), f_no, "Manuel Giriş", t_excel, "BORÇ" if "BORÇ" in tip else "ALACAK"])
                st.success(f"Kaydedildi: {t_excel} TL")
                st.rerun()

    if m_data:
        df_cari = pd.DataFrame(m_data)
        secili = st.selectbox("Hesap Seç:", df_cari['Cari Adı'].unique())
        if secili:
            sub = df_cari[df_cari['Cari Adı'] == secili].copy()
            sub['T_Float'] = sub['Tutar'].apply(safe_float)
            st.table(sub[["Tarih", "Fatura No", "Tutar", "Tip"]])
            borc = sub[sub['Tip'] == "BORÇ"]['T_Float'].sum()
            alacak = sub[sub['Tip'] == "ALACAK"]['T_Float'].sum()
            st.metric("GÜNCEL BAKİYE", format_excel_tl(alacak - borc))

# 2. SİPARİŞ LİSTESİ (BASİT)
elif menu == "📋 Sipariş Listesi":
    st.header("Siparişler")
    data = verileri_getir("Siparisler")
    if data: st.dataframe(pd.DataFrame(data), use_container_width=True)

# 7. MALİYET VE 8. ÜRÜN (KISALTILMIŞ)
elif menu == "📉 Maliyet Yönetimi":
    st.header("Ürün Maliyetleri")
    data = verileri_getir("Maliyetler")
    if data: st.dataframe(pd.DataFrame(data))

elif menu == "➕ Ürün Yönetimi":
    st.header("Ürün Ekle")
    with st.form("u_e"):
        ad = st.text_input("Ürün Adı")
        if st.form_submit_button("EKLE"):
            yeni_urun_resim_ekle(ad, "yok.jpg")
            st.success("Eklendi")
