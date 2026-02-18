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

# --- GÜVENLİ SAYI DÖNÜŞTÜRME (ULTRA GÜVENLİ) ---
def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0
        # Önce float'a çevirip sonra integer yapıyoruz
        return int(safe_float(val))
    except: return 0

def safe_float(val):
    """Excel'deki '51.805,20' metnini hatasız matematiksel sayıya çevirir."""
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        if isinstance(val, (int, float)): return float(val)
        
        # TL simgesi ve boşlukları temizle
        s = str(val).replace("TL", "").replace("tl", "").replace("₺", "").replace(" ", "").strip()
        
        # TÜRKÇE FORMAT DÜZELTME (51.805,20 -> 51805.20)
        if "." in s and "," in s:
            # Nokta binlik ayracıdır (sil), Virgül kuruş ayracıdır (nokta yap)
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            # Sadece virgül varsa (1250,50 -> 1250.50)
            s = s.replace(",", ".")
        # Sadece nokta varsa, binlik mi kuruş mu kontrolü (TR formatı varsayılan)
        elif "." in s:
            # Eğer noktadan sonra tam 2 hane varsa kuruş noktasıdır, 3 hane varsa binliktir.
            parts = s.split(".")
            if len(parts[-1]) != 2: # Binlik noktası varsayalım
                s = s.replace(".", "")
            
        return float(s)
    except:
        return 0.0

def format_para_tr(val):
    """Matematiksel sayıyı 51.805,20 TL metnine çevirir."""
    try:
        # Önce standart 1,250.50 yap, sonra virgül/nokta takas et
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
    except gspread.exceptions.WorksheetNotFound:
        return []
    except Exception as e:
        return []

def cache_temizle():
    st.cache_data.clear()

def siparis_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Siparisler")
    except:
        w = sh.add_worksheet(title="Siparisler", rows=100, cols=20)
        w.append_row(["Siparis No","Tarih","Durum","Müşteri","Telefon","TC No","Mail","Ürün 1","Adet 1","İsim 1","Ürün 2","Adet 2","İsim 2","Tutar","Ödeme","Kaynak","Adres","Not","Fatura Durumu","Tedarik Durumu"])
    w.append_row(satir)
    cache_temizle()

def cari_islem_ekle(satir):
    sh = get_sheet()
    try: w = sh.worksheet("Cariler")
    except:
        w = sh.add_worksheet(title="Cariler", rows=100, cols=6)
        w.append_row(["Cari Adı", "Tarih", "Fatura No", "Not", "Tutar", "Tip"])
    w.append_row(satir)
    cache_temizle()

# --- ÖZEL FONKSİYONLAR ---
def fatura_durumunu_kesildi_yap(siparis_nolar):
    sh = get_sheet()
    w = sh.worksheet("Siparisler")
    try:
        headers = w.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        fatura_col = headers.index("Fatura Durumu") + 1
        for sip_no in siparis_nolar:
            cell = w.find(str(sip_no), in_column=sip_no_col)
            if cell: w.update_cell(cell.row, fatura_col, "KESİLDİ")
        cache_temizle()
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

def tedarik_durumunu_guncelle_ve_cariye_isle(siparis_bilgileri, cari_hesap, maliyet_sozlugu):
    sh = get_sheet()
    ws_siparis = sh.worksheet("Siparisler")
    ws_cari = sh.worksheet("Cariler")
    tarih_str = simdi().strftime("%d.%m.%Y")
    
    try:
        headers = ws_siparis.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        try: tedarik_col = headers.index("Tedarik Durumu") + 1
        except: return "HATA: 'Siparisler' sayfasında 'Tedarik Durumu' sütunu yok."

        toplam_maliyet = 0
        islenen_nolar = []

        for sip in siparis_bilgileri:
            sip_no = sip['Siparis No']
            u1, a1 = sip.get('Ürün 1', ''), safe_int(sip.get('Adet 1', 0))
            u2, a2 = sip.get('Ürün 2', ''), safe_int(sip.get('Adet 2', 0))
            toplam_maliyet += (maliyet_sozlugu.get(u1, 0) * a1) + (maliyet_sozlugu.get(u2, 0) * a2)
            islenen_nolar.append(str(sip_no))
            cell = ws_siparis.find(str(sip_no), in_column=sip_no_col)
            if cell: ws_siparis.update_cell(cell.row, tedarik_col, "TEDARİKÇİ KESTİ")

        # KDV Dahil Maliyet ve Metin Olarak Biçimlendirme
        tutar_kdv_dahil = toplam_maliyet * 1.20
        tutar_formatli = format_para_tr(tutar_kdv_dahil)
        aciklama = f"Sipariş Maliyetleri: {', '.join(islenen_nolar)}"
        ws_cari.append_row([cari_hesap, tarih_str, "OTO-ALIS", aciklama, tutar_formatli, "BORÇ"])
        
        cache_temizle()
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

def alis_faturasi_onayla(alis_indexler):
    sh = get_sheet()
    try: ws_alis = sh.worksheet("Alislar")
    except: return "Alislar sayfası yok"
    try: ws_cari = sh.worksheet("Cariler")
    except: 
        ws_cari = sh.add_worksheet(title="Cariler", rows=100, cols=6)
        ws_cari.append_row(["Cari Adı", "Tarih", "Fatura No", "Not", "Tutar", "Tip"])
    
    tarih_str = simdi().strftime("%d.%m.%Y")
    try:
        headers = ws_alis.row_values(1)
        durum_col = headers.index("Durum") + 1
        for row_num, cari_hesap, net_tutar, aciklama in alis_indexler:
            ws_alis.update_cell(row_num + 2, durum_col, "FATURALAŞTI")
            brut_val = format_para_tr(safe_float(net_tutar) * 1.20)
            ws_cari.append_row([cari_hesap, tarih_str, "ALIS-FAT", aciklama, brut_val, "BORÇ"])
        cache_temizle()
        return "BAŞARILI"
    except Exception as e: return f"HATA: {e}"

def get_maliyet_dict():
    maliyetler = verileri_getir("Maliyetler")
    m_dict = {}
    if maliyetler:
        for m in maliyetler:
            u_id = m.get("Ürün Id") or m.get("Urun Id")
            cost = safe_float(m.get("MALİYET") or m.get("Maliyet"))
            if u_id: m_dict[u_id] = cost
    return m_dict

def get_urun_resimleri():
    sabitler = {"Logo": "logo.png"}
    db_urunler = verileri_getir("Urunler")
    for u in db_urunler:
        if isinstance(u, dict) and "Urun Adi" in u:
            sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

GUNCEL_URUNLER = get_urun_resimleri()

# --- PDF OLUŞTURMA ---
def create_pdf(s, urun_dict):
    pdf = FPDF()
    pdf.add_page()
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.text(150, 15, f"SipNo: #{s.get('Siparis No')}"); pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")
    pdf.set_y(110); pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 10, f"Müşteri: {s.get('Müşteri')}", ln=1)
    pdf.cell(0, 10, f"Tutar: {format_para_tr(safe_float(s.get('Tutar')))} TL", ln=1)
    return pdf.output(dest='S').encode('latin-1')

# --- MENÜ ---
menu_options = ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"]
menu = st.sidebar.radio("Menü", menu_options)

# 1. SİPARİŞ GİRİŞİ
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        u1 = st.selectbox("1. Ürün Seçimi", list(GUNCEL_URUNLER.keys()))
        a1 = st.number_input("1. Ürün Adet", 1, 100, 1)
        ikinci = st.checkbox("2. Ürün Ekle (+)")
        u2, a2 = "", ""
        if ikinci:
            u2 = st.selectbox("2. Ürün Seçimi", list(GUNCEL_URUNLER.keys()), key="u2_s")
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_n")
    with col2:
        with st.form("siparis"):
            c1, c2 = st.columns(2)
            t_inp = c1.text_input("Tutar (KDV DAHİL - Örn: 51.805,20)")
            if t_inp: c1.caption(f"Sistem Algıladı: {format_para_tr(safe_float(t_inp))} TL")
            odeme = c2.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            durum = st.selectbox("Durum", ["YENİ SİPARİŞ", "KARGOLANDI", "TESLİM EDİLDİ"])
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            adres = st.text_area("Adres", height=100)
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"
            if st.form_submit_button("KAYDET", type="primary"):
                try:
                    mevcut = verileri_getir("Siparisler")
                    y_no = 1000
                    if mevcut:
                        df_m = pd.DataFrame(mevcut)
                        if not df_m.empty: y_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                    tutar_str = format_para_tr(safe_float(t_inp))
                    satir = [y_no, simdi().strftime("%d.%m.%Y %H:%M"), durum, ad, tel, "", "", u1, a1, "", u2, a2, "", tutar_str, odeme, "Web", adres, "", fatura, "BEKLİYOR"]
                    siparis_ekle(satir)
                    st.success(f"✅ Sipariş #{y_no} Kaydedildi!")
                except Exception as e: st.error(f"Hata: {e}")

# 2. SİPARİŞ LİSTESİ
elif menu == "📋 Sipariş Listesi":
    st.header("Sipariş Geçmişi")
    data = verileri_getir("Siparisler")
    if data:
        df = pd.DataFrame(data)
        if 'Siparis No' in df.columns:
            df['Siparis No'] = pd.to_numeric(df['Siparis No'], errors='coerce')
            df = df.sort_values(by="Siparis No", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.divider()
        secilen = st.selectbox("Fiş Yazdır:", df.apply(lambda x: f"{int(x['Siparis No'])} - {x['Müşteri']}", axis=1))
        if st.button("📄 FİŞ OLUŞTUR"):
            s_no = int(secilen.split(" - ")[0])
            sip = df[df['Siparis No'] == s_no].iloc[0].to_dict()
            pdf_data = create_pdf(sip, GUNCEL_URUNLER)
            st.download_button("📥 İNDİR", pdf_data, f"Siparis_{s_no}.pdf", "application/pdf")

# 4. ALIŞ VE TEDARİK
elif menu == "🧾 Alış ve Tedarik":
    st.header("Tedarikçi Alış Yönetimi")
    c_data = verileri_getir("Cariler")
    c_list = sorted(list(set([r['Cari Adı'] for r in c_data if r['Cari Adı']]))) if c_data else []
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
                if res == "BAŞARILI": st.success("✅ İşlendi!"); st.rerun()
        else: st.success("Tüm tedarikler tamam!")

# 6. CARİ HESAPLAR (BAKİYE HESAPLAMA DÜZELTİLDİ)
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    m_data = verileri_getir("Cariler")
    with st.expander("➕ Yeni Fatura / Ödeme İşle", expanded=True):
        with st.form("cari"):
            c1, c2 = st.columns(2)
            c_list = sorted(list(set([r['Cari Adı'] for r in m_data]))) if m_data else []
            ad_sec = c1.selectbox("Cari Hesap:", ["Yeni Ekle..."] + c_list)
            if ad_sec == "Yeni Ekle...": ad = c1.text_input("Yeni Cari Adı:")
            else: ad = ad_sec
            f_no = c2.text_input("Fatura No")
            not_ac = st.text_input("Not")
            t_inp = st.text_input("Tutar (KDV DAHİL - Örn: 51.805,20)")
            if t_inp: st.caption(f"Sistem Algıladı: {format_para_tr(safe_float(t_inp))} TL")
            tip = st.radio("İşlem Türü:", ["Fatura Girişi (BORÇ)", "ÖDEME YAPILDI (ALACAK)"])
            if st.form_submit_button("KAYDET"):
                if ad and t_inp:
                    t_val_formatli = format_para_tr(safe_float(t_inp))
                    cari_islem_ekle([ad, simdi().strftime("%d.%m.%Y"), f_no, not_ac, t_val_formatli, "BORÇ" if "BORÇ" in tip else "ALACAK"])
                    st.success(f"✅ Kaydedildi! ({t_val_formatli} TL)")
                    st.rerun()

    if m_data:
        df = pd.DataFrame(m_data)
        if 'Cari Adı' in df.columns:
            secili = st.selectbox("Hesap Detayı Gör:", df['Cari Adı'].unique())
            if secili:
                sub = df[df['Cari Adı'] == secili].copy()
                # KRİTİK HESAPLAMA MOTORU:
                sub['Matematiksel_Tutar'] = sub['Tutar'].apply(safe_float)
                st.table(sub[["Tarih", "Fatura No", "Not", "Tutar", "Tip"]])
                
                borc = sub[sub['Tip'] == "BORÇ"]['Matematiksel_Tutar'].sum()
                alacak = sub[sub['Tip'] == "ALACAK"]['Matematiksel_Tutar'].sum()
                bakiye = alacak - borc
                
                k1, k2, k3 = st.columns(3)
                k1.metric("Toplam Borç", format_para_tr(borc))
                k2.metric("Toplam Ödeme", format_para_tr(alacak))
                st.divider()
                st.subheader(f"GÜNCEL BAKİYE (Alacak - Borç): {format_para_tr(bakiye)} TL")

# 7. MALİYET YÖNETİMİ
elif menu == "📉 Maliyet Yönetimi":
    st.header("Ürün Maliyet Yönetimi")
    try:
        maliyet_data = verileri_getir("Maliyetler")
        if maliyet_data:
            df_m = pd.DataFrame(maliyet_data)
            st.dataframe(df_m, use_container_width=True)
    except: st.error("Maliyet verisi okunamadı.")
