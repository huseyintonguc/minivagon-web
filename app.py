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

# --- GÜVENLİ SAYI DÖNÜŞTÜRME ---
def safe_int(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0
        return int(float(str(val).replace(",", ".")))
    except: return 0

def safe_float(val):
    try:
        if pd.isna(val) or str(val).strip() == "": return 0.0
        return float(str(val).replace("TL","").replace(".","").replace(",", "."))
    except: return 0.0

# --- VERİ İŞLEMLERİ (CACHING) ---
@st.cache_data(ttl=10)
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
        w = sh.add_worksheet(title="Siparisler", rows=100, cols=25)
        # Sütun başlıklarını güncelle
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

def yeni_urun_resim_ekle(ad, resim_adi):
    sh = get_sheet()
    try: w = sh.worksheet("Urunler")
    except: 
        w = sh.add_worksheet(title="Urunler", rows=100, cols=2)
        w.append_row(["Urun Adi", "Resim Dosya Adi"])
    w.append_row([ad, resim_adi])
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
    """
    Siparişlerin 'Tedarik Durumu'nu günceller ve maliyetleri hesaplayıp cariye işler.
    siparis_bilgileri: List of dicts (Order rows)
    """
    sh = get_sheet()
    ws_siparis = sh.worksheet("Siparisler")
    ws_cari = sh.worksheet("Cariler")
    tarih_str = simdi().strftime("%d.%m.%Y")
    
    try:
        headers = ws_siparis.row_values(1)
        sip_no_col = headers.index("Siparis No") + 1
        
        # Eğer Tedarik Durumu sütunu yoksa en sona eklemeyi dene veya hata ver
        try:
            tedarik_col = headers.index("Tedarik Durumu") + 1
        except:
            return "HATA: 'Siparisler' sayfasında 'Tedarik Durumu' sütunu bulunamadı."

        toplam_maliyet = 0
        islenen_siparis_nolar = []

        for sip in siparis_bilgileri:
            sip_no = sip['Siparis No']
            u1 = sip.get('Ürün 1', '')
            a1 = safe_int(sip.get('Adet 1', 0))
            u2 = sip.get('Ürün 2', '')
            a2 = safe_int(sip.get('Adet 2', 0))
            
            # Maliyet Hesapla
            maliyet1 = maliyet_sozlugu.get(u1, 0) * a1
            maliyet2 = maliyet_sozlugu.get(u2, 0) * a2
            toplam_maliyet += (maliyet1 + maliyet2)
            
            islenen_siparis_nolar.append(str(sip_no))
            
            # Durumu Güncelle
            cell = ws_siparis.find(str(sip_no), in_column=sip_no_col)
            if cell:
                ws_siparis.update_cell(cell.row, tedarik_col, "TEDARİKÇİ KESTİ")

        # Cariye İşle (KDV Dahil mi Hariç mi? Maliyet tablosu genelde maliyettir. 
        # Kullanıcı "KDV Dahil olacak" demişti önceki promptta cari için.
        # Biz maliyet tablosundan gelen veriyi baz alıyoruz. Maliyet tablosu ham maliyet ise üstüne KDV eklenebilir.
        # Varsayılan olarak Maliyet Tablosundaki rakam * 1.20 (KDV) yapalım.)
        
        tutar_kdv_dahil = toplam_maliyet * 1.20
        aciklama = f"Toplu Tedarik Faturası (Siparişler: {', '.join(islenen_siparis_nolar)})"
        
        # [Cari Adı, Tarih, Fatura No, Not, Tutar, Tip]
        ws_cari.append_row([cari_hesap, tarih_str, "TOPLU-ALIS", aciklama, tutar_kdv_dahil, "BORÇ"])
        
        cache_temizle()
        return "BAŞARILI"
    
    except Exception as e: return f"HATA: {e}"

def maliyet_kaydet(veriler):
    sh = get_sheet()
    try: w = sh.worksheet("Maliyetler")
    except: return "Maliyetler sayfası bulunamadı."
    tum = w.get_all_records()
    df = pd.DataFrame(tum)
    yeni = [veriler.get("Görsel",""), veriler.get("Ürün Kod",""), veriler.get("Ürün Id",""), veriler.get("Tahta",0), veriler.get("VERNİK",0), veriler.get("YAKMA",0), veriler.get("BOYA",0), veriler.get("MUSLUK",0), veriler.get("BORU",0), veriler.get("HALAT",0), veriler.get("Metal çubuk",0), veriler.get("CAM",0), veriler.get("UĞUR KAR",0), veriler.get("MALİYET",0)]
    try:
        col = "Ürün Id"
        if col not in df.columns: 
            if "Urun Id" in df.columns: col="Urun Id"
            elif "Ürün ID" in df.columns: col="Ürün ID"
            else: return "HATA: Sütun yok"
        idx = df.index[df[col].astype(str) == str(veriler["Ürün Id"])].tolist()
        if idx:
            r = idx[0] + 2
            w.update(f"A{r}:N{r}", [yeni])
            cache_temizle()
            return "GÜNCELLENDİ"
        w.append_row(yeni)
        cache_temizle()
        return "EKLENDİ"
    except Exception as e: return f"HATA: {e}"

# --- ÜRÜNLERİ GETİR ---
def get_urun_resimleri():
    sabitler = {
        "6 LI KADEHLİK": "6likadehlik.jpg", "2 LI KALPLİ KADEHLİK": "2likalplikadehlik.jpg",
        "3 LÜ KADEHLİK": "3lukadehlik.jpg", "İKİLİ STAND": "ikilistand.jpg",
        "ÇİFTLİ FIÇI": "ciftlifici.jpg", "TEKLİ FIÇI": "teklifici.jpg",
        "TEKLİ STAND": "teklistand.jpg", "TEKLİ STAND RAFLI": "teklistandrafli.jpg",
        "Viski Çerezlik": "tekliviski.jpg", "SATRANÇ": "satranc.jpg",
        "ALTIGEN": "altigen.jpg", "MAÇA AS": "macaas.jpg",
        "KUPA AS": "kupaas.jpg", "KARO AS": "karoas.jpg",
        "SİNEK AS": "sinekas.jpg", "YANIK NARGİLE SEHPA": "yaniknargilesehpa.jpg",
        "AÇIK RENK NARGİLE SEHPA": "acikrenknargilesehpa.jpg", "SİYAH TEKLİ STAND": "syhteklistand.jpg"
    }
    db_urunler = verileri_getir("Urunler")
    for u in db_urunler:
        if isinstance(u, dict) and "Urun Adi" in u and "Resim Dosya Adi" in u:
            sabitler[u["Urun Adi"]] = u["Resim Dosya Adi"]
    return sabitler

GUNCEL_URUNLER = get_urun_resimleri()

# --- MALİYET SÖZLÜĞÜ GETİR ---
def get_maliyet_dict():
    maliyetler = verileri_getir("Maliyetler")
    m_dict = {}
    if maliyetler:
        for m in maliyetler:
            # Ürün Id ve MALİYET sütunlarını kullan
            # Sütun isimleri Excel'deki gibi olmalı
            u_id = m.get("Ürün Id") or m.get("Urun Id")
            cost = safe_float(m.get("MALİYET") or m.get("Maliyet"))
            if u_id:
                m_dict[u_id] = cost
    return m_dict

# --- PDF OLUŞTURMA ---
def create_pdf(s, urun_dict):
    pdf = FPDF()
    pdf.add_page()
    try: pdf.add_font('ArialTR', '', 'arial.ttf', uni=True); pdf.set_font('ArialTR', '', 12)
    except: pdf.set_font("Arial", size=12)
    pdf.set_fill_color(40, 40, 40); pdf.rect(0, 0, 210, 30, 'F')
    pdf.set_text_color(255, 255, 255); pdf.set_font_size(20); pdf.text(10, 20, "MINIVAGON")
    pdf.set_font_size(10); pdf.set_text_color(200, 200, 200)
    pdf.text(150, 15, f"Siparis No: #{s.get('Siparis No')}")
    pdf.text(150, 22, f"Tarih: {s.get('Tarih')}")
    def resim_koy(u_adi, x_pos):
        if u_adi in urun_dict:
            dosya_adi = urun_dict[u_adi]
            full_path = os.path.join(RESIM_KLASORU, dosya_adi)
            if os.path.exists(full_path):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        img = Image.open(full_path).convert('RGB'); img.thumbnail((300, 220)); img.save(tmp.name)
                        pdf.image(tmp.name, x=x_pos, y=40, h=60)
                except: pass
    if s.get('Ürün 2'): resim_koy(s.get('Ürün 1'), 15); resim_koy(s.get('Ürün 2'), 110)
    else: resim_koy(s.get('Ürün 1'), 65)
    pdf.set_y(110); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12)
    def tr(t): return str(t).replace("ğ","g").replace("Ğ","G").replace("ş","s").replace("Ş","S").replace("İ","I").replace("ı","i").encode('latin-1','replace').decode('latin-1') if t else ""
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  URUN DETAYLARI", ln=1, fill=True); pdf.ln(2)
    ek1 = f" - Isim: {s.get('İsim 1')}" if s.get('İsim 1') else ""
    pdf.cell(0, 8, tr(f"1) {s.get('Ürün 1')} ({s.get('Adet 1')} Adet){ek1}"), ln=1)
    if s.get('Ürün 2'): ek2 = f" - Isim: {s.get('İsim 2')}" if s.get('İsim 2') else ""; pdf.cell(0, 8, tr(f"2) {s.get('Ürün 2')} ({s.get('Adet 2')} Adet){ek2}"), ln=1)
    pdf.ln(5)
    if "KAPIDA" in str(s.get('Ödeme')):
        pdf.set_fill_color(255, 230, 100); pdf.rect(10, pdf.get_y(), 190, 25, 'F'); pdf.set_xy(12, pdf.get_y()+2)
        pdf.cell(0, 10, tr(f"ODEME: {s.get('Ödeme')}"), ln=1); pdf.set_text_color(200, 0, 0); pdf.set_font_size(16)
        pdf.cell(0, 10, tr(f"TAHSIL EDILECEK TUTAR: {s.get('Tutar')} TL"), ln=1); pdf.set_text_color(0, 0, 0); pdf.set_font_size(12); pdf.ln(5)
    else: pdf.cell(0, 10, tr(f"Odeme: {s.get('Ödeme')} | Tutar: {s.get('Tutar')} TL"), ln=1); pdf.ln(5)
    pdf.set_fill_color(240, 240, 240); pdf.cell(0, 10, "  MUSTERI BILGILERI", ln=1, fill=True); pdf.ln(2)
    pdf.cell(0, 8, tr(f"Musteri: {s.get('Müşteri')}"), ln=1); pdf.cell(0, 8, tr(f"Telefon: {s.get('Telefon')}"), ln=1)
    pdf.multi_cell(0, 8, tr(f"Adres: {s.get('Adres')}"))
    if s.get('Not'): pdf.multi_cell(0, 8, tr(f"NOT: {s.get('Not')}"))
    return pdf.output(dest='S').encode('latin-1')

# --- MENÜ ---
menu_options = ["📦 Sipariş Girişi", "📋 Sipariş Listesi", "🧾 Fatura Takibi", "🧾 Alış ve Tedarik", "📊 Raporlar", "💰 Cari Hesaplar", "📉 Maliyet Yönetimi", "➕ Ürün Yönetimi"]
menu = st.sidebar.radio("Menü", menu_options)

# 1. SİPARİŞ GİRİŞİ
if menu == "📦 Sipariş Girişi":
    st.header("Yeni Sipariş Ekle")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.info("🛒 Ürün Bilgileri")
        u1 = st.selectbox("1. Ürün Seçimi", list(GUNCEL_URUNLER.keys()))
        if u1 in GUNCEL_URUNLER and os.path.exists(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u1])):
            st.image(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u1]), width=250)
        a1 = st.number_input("1. Ürün Adet", 1, 100, 1)
        i1 = st.text_input("1. Ürün Özel İsim")
        st.markdown("---")
        ikinci = st.checkbox("2. Ürün Ekle (+)")
        u2, a2, i2 = "", "", ""
        if ikinci:
            u2 = st.selectbox("2. Ürün Seçimi", list(GUNCEL_URUNLER.keys()), key="u2_sel")
            if u2 in GUNCEL_URUNLER and os.path.exists(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u2])):
                st.image(os.path.join(RESIM_KLASORU, GUNCEL_URUNLER[u2]), width=250)
            a2 = st.number_input("2. Ürün Adet", 1, 100, 1, key="a2_n")
            i2 = st.text_input("2. Ürün Özel İsim", key="i2_t")
    with col2:
        st.info("💳 Müşteri ve Finans")
        with st.form("siparis"):
            c1, c2 = st.columns(2)
            tutar = c1.text_input("Tutar (TL)")
            odeme = c2.selectbox("Ödeme", ["KAPIDA NAKİT", "KAPIDA K.KARTI", "HAVALE/EFT", "WEB SİTESİ"])
            c3, c4 = st.columns(2)
            kaynak = c3.selectbox("Kaynak", ["Instagram", "Web Sitesi", "Trendyol", "Whatsapp"])
            durum = c4.selectbox("Durum", ["YENİ SİPARİŞ", "KARGOLANDI", "TESLİM EDİLDİ"])
            st.divider()
            ad = st.text_input("Ad Soyad")
            tel = st.text_input("Telefon")
            tc = st.text_input("TC (Opsiyonel)")
            mail = st.text_input("Mail (Opsiyonel)")
            adres = st.text_area("Adres", height=100)
            notlar = st.text_input("Not")
            fatura = "KESİLDİ" if st.checkbox("Faturası Kesildi") else "KESİLMEDİ"
            # Varsayılan Tedarik Durumu
            tedarik = "BEKLİYOR"
            
            if st.form_submit_button("KAYDET", type="primary"):
                try:
                    mevcut = verileri_getir("Siparisler")
                    yeni_no = 1000
                    if mevcut:
                        df_m = pd.DataFrame(mevcut)
                        if not df_m.empty and 'Siparis No' in df_m.columns:
                            try: yeni_no = int(pd.to_numeric(df_m['Siparis No'], errors='coerce').max()) + 1
                            except: pass
                    tarih = simdi().strftime("%d.%m.%Y %H:%M")
                    satir = [yeni_no, tarih, durum, ad, tel, tc, mail, u1, a1, i1, u2, a2, i2, tutar, odeme, kaynak, adres, notlar, fatura, tedarik]
                    siparis_ekle(satir)
                    st.success(f"✅ Sipariş #{yeni_no} Kaydedildi!")
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
        col1, col2 = st.columns([3, 1])
        arama = col1.text_input("Arama")
        if arama: df = df[df.astype(str).apply(lambda x: x.str.contains(arama, case=False)).any(axis=1)]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.divider()
        if 'Siparis No' in df.columns and not df.empty:
            secenekler = df.apply(lambda x: f"{int(x['Siparis No'])} - {x['Müşteri']}", axis=1)
            secilen = st.selectbox("Fiş Yazdır:", secenekler)
            if st.button("📄 FİŞ OLUŞTUR"):
                s_no = int(secilen.split(" - ")[0])
                sip = df[df['Siparis No'] == s_no].iloc[0].to_dict()
                pdf_data = create_pdf(sip, GUNCEL_URUNLER)
                st.download_button("📥 İNDİR", pdf_data, f"Siparis_{s_no}.pdf", "application/pdf", type="primary")

# 3. FATURA TAKİBİ
elif menu == "🧾 Fatura Takibi":
    st.header("Müşteri Fatura Yönetimi")
    try:
        raw_data = verileri_getir("Siparisler")
        if raw_data:
            df = pd.DataFrame(raw_data)
            df['Tutar_float'] = df['Tutar'].apply(lambda x: safe_float(x))
            if "Fatura Durumu" not in df.columns: st.error("Veritabanında 'Fatura Durumu' sütunu bulunamadı.")
            else:
                tab1, tab2 = st.tabs(["🔴 Kesilecekler", "🟢 Kesilenler"])
                with tab1:
                    bekleyenler = df[df["Fatura Durumu"] != "KESİLDİ"].copy()
                    if not bekleyenler.empty:
                        st.metric("Bekleyen Tutar", f"{bekleyenler['Tutar_float'].sum():,.2f} TL")
                        st.dataframe(bekleyenler[["Siparis No", "Tarih", "Müşteri", "Tutar", "Fatura Durumu"]], use_container_width=True)
                        secenekler = bekleyenler.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']} ({x['Tutar']})", axis=1).tolist()
                        secilen_faturalar = st.multiselect("Kesildi İşaretle:", secenekler)
                        if st.button("ONAYLA"):
                            if secilen_faturalar:
                                siparis_nolar = [int(s.split(" - ")[0]) for s in secilen_faturalar]
                                sonuc = fatura_durumunu_kesildi_yap(siparis_nolar)
                                if sonuc == "BAŞARILI":
                                    st.success("Güncellendi!")
                                    st.rerun()
                                else: st.error(sonuc)
                    else: st.success("Kesilecek fatura kalmadı.")
                with tab2:
                    kesilenler = df[df["Fatura Durumu"] == "KESİLDİ"]
                    st.dataframe(kesilenler[["Siparis No", "Tarih", "Müşteri", "Tutar", "Fatura Durumu"]], use_container_width=True)
    except Exception as e: st.error(f"Hata: {e}")

# 4. ALIŞ VE TEDARİK (YENİLENDİ: SİPARİŞ LİSTESİNDEN SEÇMELİ)
elif menu == "🧾 Alış ve Tedarik":
    st.header("Tedarikçi Alış Yönetimi")
    
    # Cari Hesaplarını Çek
    cariler_data = verileri_getir("Cariler")
    cari_listesi = []
    if cariler_data:
        df_cariler = pd.DataFrame(cariler_data)
        if "Cari Adı" in df_cariler.columns:
            cari_listesi = df_cariler["Cari Adı"].unique().tolist()
            
    # Maliyetleri Çek
    maliyet_sozlugu = get_maliyet_dict()

    if not cari_listesi:
        st.warning("Lütfen önce 'Cari Hesaplar' bölümünden tedarikçi (cari) oluşturun.")
    else:
        # Sipariş Verilerini Çek
        siparis_data = verileri_getir("Siparisler")
        if siparis_data:
            df_siparis = pd.DataFrame(siparis_data)
            
            if "Tedarik Durumu" not in df_siparis.columns:
                st.error("⚠️ Lütfen Google Sheets 'Siparisler' sayfasının en sağına 'Tedarik Durumu' başlığı ekleyin.")
            else:
                # Sadece tedarik edilmemişleri göster
                bekleyenler = df_siparis[df_siparis["Tedarik Durumu"] != "TEDARİKÇİ KESTİ"].copy()
                
                if not bekleyenler.empty:
                    st.info("Aşağıdaki listeden tedarikçisi faturasını kesen siparişleri seçin.")
                    
                    # Cari Seçimi
                    secilen_cari = st.selectbox("Hangi Tedarikçi Kesti?", cari_listesi)
                    
                    # Tabloyu Göster
                    st.dataframe(bekleyenler[["Siparis No", "Müşteri", "Ürün 1", "Adet 1", "Ürün 2", "Adet 2"]], use_container_width=True)
                    
                    st.markdown("### ✅ İşlem Yap")
                    
                    # Çoklu Seçim
                    secenekler = bekleyenler.apply(lambda x: f"{x['Siparis No']} - {x['Müşteri']} ({x['Ürün 1']})", axis=1).tolist()
                    secilen_siparisler = st.multiselect("Faturası Gelen Siparişleri Seç:", secenekler)
                    
                    col_b1, col_b2 = st.columns(2)
                    
                    with col_b1:
                        if st.button("SEÇİLENLERİN FATURASI KESİLDİ & CARİYE İŞLE"):
                            if secilen_siparisler:
                                secilen_nolar = [int(s.split(" - ")[0]) for s in secilen_siparisler]
                                # İlgili satırları bul
                                islenecek_satirlar = bekleyenler[bekleyenler['Siparis No'].isin(secilen_nolar)].to_dict('records')
                                
                                sonuc = tedarik_durumunu_guncelle_ve_cariye_isle(islenecek_satirlar, secilen_cari, maliyet_sozlugu)
                                if sonuc == "BAŞARILI":
                                    st.success("✅ Seçilen siparişler güncellendi ve cariye işlendi!")
                                    st.rerun()
                                else: st.error(sonuc)
                            else: st.warning("Lütfen en az bir sipariş seçin.")
                    
                    with col_b2:
                        st.write("")
                        if st.button("LİSTEDEKİ HEPSİNİ ONAYLA (TOPLU)", type="primary"):
                            islenecek_satirlar = bekleyenler.to_dict('records')
                            sonuc = tedarik_durumunu_guncelle_ve_cariye_isle(islenecek_satirlar, secilen_cari, maliyet_sozlugu)
                            if sonuc == "BAŞARILI":
                                st.success("🚀 Tüm liste güncellendi ve cariye işlendi!")
                                st.rerun()
                            else: st.error(sonuc)
                else:
                    st.success("Tüm siparişlerin tedarik süreci tamamlanmış.")
        else:
            st.info("Henüz sipariş yok.")

# 5. RAPORLAR
elif menu == "📊 Raporlar":
    st.header("Satış Raporları")
    try:
        raw_data = verileri_getir("Siparisler")
        if raw_data:
            df = pd.DataFrame(raw_data)
            df['Tarih_dt'] = pd.to_datetime(df['Tarih'], format="%d.%m.%Y %H:%M", errors='coerce')
            df['Tarih_gun'] = df['Tarih_dt'].dt.date
            df['Tutar_float'] = df['Tutar'].apply(lambda x: safe_float(x))
            f1, f2, f3 = st.columns([1, 1, 2])
            with f1:
                secilen_urunler = st.multiselect("Ürün Seçiniz:", list(GUNCEL_URUNLER.keys()))
            with f2:
                zaman_secimi = st.selectbox("Dönem:", ["Bugün", "Dün", "Bu Ay", "Geçen Ay", "Son 7 Gün", "Son 30 Gün", "Son 1 Yıl", "Tarih Aralığı Seç"])

            bugun = simdi().date()
            bas, bit = bugun, bugun

            if zaman_secimi == "Bugün": pass
            elif zaman_secimi == "Dün": bas = bugun - timedelta(days=1); bit = bas
            elif zaman_secimi == "Son 7 Gün": bas = bugun - timedelta(days=7)
            elif zaman_secimi == "Son 30 Gün": bas = bugun - timedelta(days=30)
            elif zaman_secimi == "Son 1 Yıl": bas = bugun - timedelta(days=365)
            elif zaman_secimi == "Bu Ay": bas = bugun.replace(day=1)
            elif zaman_secimi == "Geçen Ay":
                bu_ay_ilk = bugun.replace(day=1)
                gecen_ay_son = bu_ay_ilk - timedelta(days=1)
                bas = gecen_ay_son.replace(day=1); bit = gecen_ay_son
            elif zaman_secimi == "Tarih Aralığı Seç":
                with f3:
                    d_range = st.date_input("Aralık:", (bugun - timedelta(days=7), bugun))
                    if len(d_range) == 2: bas, bit = d_range

            df_f = df[(df['Tarih_gun'] >= bas) & (df['Tarih_gun'] <= bit)]
            if secilen_urunler:
                df_f = df_f[df_f['Ürün 1'].isin(secilen_urunler) | df_f['Ürün 2'].isin(secilen_urunler)]

            if not df_f.empty:
                st.info(f"📅 {bas.strftime('%d.%m.%Y')} - {bit.strftime('%d.%m.%Y')}")
                top_ciro = df_f['Tutar_float'].sum()
                top_sip = len(df_f)
                a1 = pd.to_numeric(df_f['Adet 1'], errors='coerce').fillna(0).sum()
                a2 = pd.to_numeric(df_f['Adet 2'], errors='coerce').fillna(0).sum()
                top_urun = a1 + a2

                k1, k2, k3 = st.columns(3)
                k1.metric("Toplam Ciro", f"{top_ciro:,.2f} TL")
                k2.metric("Sipariş Sayısı", f"{top_sip}")
                k3.metric("Satılan Ürün", f"{int(top_urun)}")

                g1, g2 = st.columns(2)
                with g1:
                    u1c = df_f['Ürün 1'].value_counts()
                    u2c = df_f['Ürün 2'].value_counts()
                    total = u1c.add(u2c, fill_value=0).sort_values(ascending=True)
                    if '' in total.index: total = total.drop('')
                    if not total.empty:
                        fig = px.bar(x=total.values, y=total.index, orientation='h', labels={'x':'Adet','y':''})
                        st.plotly_chart(fig, use_container_width=True)
                with g2:
                    if not df_f.empty:
                        df_grp = df_f.groupby('Tarih_gun')['Tutar_float'].sum().reset_index()
                        fig2 = px.line(df_grp, x='Tarih_gun', y='Tutar_float', markers=True)
                        st.plotly_chart(fig2, use_container_width=True)
            else: st.warning("Veri bulunamadı.")
        else: st.info("Veri yok.")
    except Exception as e: st.error(f"Hata: {e}")

# 6. CARİ HESAPLAR
elif menu == "💰 Cari Hesaplar":
    st.header("Cari Takip")
    
    with st.expander("➕ Yeni Fatura / Ödeme İşle", expanded=True):
        with st.form("cari"):
            c1, c2 = st.columns(2)
            mevcut_data = verileri_getir("Cariler")
            mevcut_cariler = []
            if mevcut_data:
                df_temp = pd.DataFrame(mevcut_data)
                if "Cari Adı" in df_temp.columns:
                    mevcut_cariler = df_temp["Cari Adı"].unique().tolist()
            cari_secim = c1.selectbox("Cari Hesap Seç:", ["Yeni Ekle..."] + mevcut_cariler)
            if cari_secim == "Yeni Ekle...": ad = c1.text_input("Yeni Cari Adı:")
            else: ad = cari_secim
            
            f_tarih = c2.date_input("Fatura Tarihi")
            f_no = c1.text_input("Fatura No")
            not_aciklama = c2.text_input("Not / Açıklama")
            tutar = st.number_input("Tutar (KDV DAHİL)", min_value=0.0, format="%.2f")
            islem_tipi = st.radio("İşlem Türü:", ["Fatura Girişi (BORÇ)", "Ödeme Yapıldı (ALACAK)"])
            
            if st.form_submit_button("KAYDET"):
                if ad:
                    # Yeni Format: [Cari Adı, Tarih, Fatura No, Not, Tutar, Tip]
                    tarih_str = f_tarih.strftime("%d.%m.%Y")
                    tip_kisa = "BORÇ" if "BORÇ" in islem_tipi else "ALACAK"
                    cari_islem_ekle([ad, tarih_str, f_no, not_aciklama, tutar, tip_kisa])
                    st.success("Kaydedildi!")
                    st.cache_resource.clear()
                    st.rerun()
                else: st.warning("Cari adı boş olamaz.")

    if mevcut_data:
        df = pd.DataFrame(mevcut_data)
        if 'Cari Adı' in df.columns:
            secili = st.selectbox("Hesap Detayı Gör:", df['Cari Adı'].unique())
            if secili:
                df['Tutar_float'] = df['Tutar'].apply(lambda x: safe_float(x))
                sub = df[df['Cari Adı'] == secili].copy()
                
                st.table(sub[["Tarih", "Fatura No", "Not", "Tutar", "Tip"]])
                
                borc = sub[sub['Tip'].astype(str).str.contains("BORÇ")]['Tutar_float'].sum()
                alacak = sub[sub['Tip'].astype(str).str.contains("ALACAK")]['Tutar_float'].sum()
                st.metric("GÜNCEL BAKİYE (Alacak - Borç)", f"{alacak - borc:,.2f} TL", delta_color="normal")
        else: st.warning("Veriler yüklenemedi, sütunları kontrol edin.")
    else: st.info("Henüz kayıt yok.")

# 7. MALİYET YÖNETİMİ
elif menu == "📉 Maliyet Yönetimi":
    st.header("Ürün Maliyet Yönetimi")
    try:
        maliyet_data = verileri_getir("Maliyetler")
        df_m = pd.DataFrame(maliyet_data)
    except: df_m = pd.DataFrame()
    tab1, tab2 = st.tabs(["📋 Liste / Detay", "➕ Ekle / Güncelle"])
    with tab1:
        if not df_m.empty:
            st.dataframe(df_m, use_container_width=True)
            if "Ürün Id" in df_m.columns:
                urunler = df_m["Ürün Id"].unique().tolist()
                secili = st.selectbox("Detay Gör:", ["Seçiniz..."] + urunler)
                if secili != "Seçiniz...":
                    detay = df_m[df_m["Ürün Id"] == secili].iloc[0]
                    c1, c2 = st.columns([1, 2])
                    c1.metric("TOPLAM MALİYET", f"{detay.get('MALİYET',0)} TL")
                    items = {k: v for k, v in detay.items() if k not in ["Görsel", "Ürün Kod", "Ürün Id", "MALİYET"] and isinstance(v, (int, float)) and v > 0}
                    c2.table(pd.DataFrame(list(items.items()), columns=["Kalem", "Tutar"]))
            else: st.warning("Excel'de 'Ürün Id' sütunu eksik.")
        else: st.warning("Maliyet tablosu boş veya okunamadı.")
    with tab2:
        st.subheader("Maliyet Kartı")
        mod = st.radio("İşlem:", ["Güncelle", "Yeni Ekle"], horizontal=True)
        vals = {}
        if mod == "Güncelle" and not df_m.empty and "Ürün Id" in df_m.columns:
            s_id = st.selectbox("Ürün Seç:", df_m["Ürün Id"].unique())
            if s_id: vals = df_m[df_m["Ürün Id"] == s_id].iloc[0].to_dict()
        with st.form("maliyet_form"):
            c1, c2 = st.columns(2)
            with c1:
                u_id = st.text_input("Ürün Adı (ID)", value=vals.get("Ürün Id", ""))
                u_kod = st.text_input("Ürün Kodu", value=vals.get("Ürün Kod", ""))
                tahta = st.number_input("Tahta", value=safe_int(vals.get("Tahta")))
                vernik = st.number_input("Vernik", value=safe_int(vals.get("VERNİK")))
                yakma = st.number_input("Yakma", value=safe_int(vals.get("YAKMA")))
                boya = st.number_input("Boya", value=safe_int(vals.get("BOYA")))
            with c2:
                musluk = st.number_input("Musluk", value=safe_int(vals.get("MUSLUK")))
                boru = st.number_input("Boru", value=safe_int(vals.get("BORU")))
                halat = st.number_input("Halat", value=safe_int(vals.get("HALAT")))
                metal = st.number_input("Metal Çubuk", value=safe_int(vals.get("Metal çubuk")))
                cam = st.number_input("Cam", value=safe_int(vals.get("CAM")))
                ugur = st.number_input("Uğur Kar", value=safe_int(vals.get("UĞUR KAR")))
            toplam = tahta+vernik+yakma+boya+musluk+boru+halat+metal+cam+ugur
            st.info(f"Hesaplanan: {toplam} TL")
            if st.form_submit_button("KAYDET"):
                veri = { "Ürün Id": u_id, "Ürün Kod": u_kod, "Görsel": GUNCEL_URUNLER.get(u_id, ""), "Tahta": tahta, "VERNİK": vernik, "YAKMA": yakma, "BOYA": boya, "MUSLUK": musluk, "BORU": boru, "HALAT": halat, "Metal çubuk": metal, "CAM": cam, "UĞUR KAR": ugur, "MALİYET": toplam }
                res = maliyet_kaydet(veri)
                if "HATA" in res: st.error(res)
                else: st.success(res); st.cache_resource.clear()

# 8. ÜRÜN YÖNETİMİ
elif menu == "➕ Ürün Yönetimi":
    st.header("Yeni Ürün Tanımla")
    with st.form("yeni_urun"):
        ad = st.text_input("Ürün Adı")
        resim = st.file_uploader("Resim", type=['jpg','png','jpeg'])
        if st.form_submit_button("EKLE"):
            if ad and resim:
                dosya = f"{ad.replace(' ','_')}.jpg"
                img = Image.open(resim).convert('RGB'); img.save(os.path.join(RESIM_KLASORU, dosya))
                yeni_urun_resim_ekle(ad, dosya)
                st.success("Eklendi!")
            else: st.warning("Eksik bilgi.")
