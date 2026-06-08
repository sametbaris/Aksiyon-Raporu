import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import io

# ================= SAYFA AYARLARI =================
st.set_page_config(page_title="Aksiyon Raporu & BBX", layout="wide", initial_sidebar_state="collapsed")

# ================= SESSION (OTURUM) YÖNETİMİ =================
if "current_view" not in st.session_state:
    st.session_state.current_view = "ana_sayfa"
if "bbx_authenticated" not in st.session_state:
    st.session_state.bbx_authenticated = False

# ================= ORTAK CSS (TASARIM) =================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    .main-title {
        text-align: left;
        background: linear-gradient(90deg, #f8f9fa, #e9ecef);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    
    .bbx-title {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
        font-family: 'Inter', sans-serif;
    }
    
    .bbx-subtitle {
        color: var(--text-color);
        opacity: 0.7;
        font-size: 1.1rem;
        margin-bottom: 1rem;
        font-family: 'Inter', sans-serif;
    }

    .metric-card {
        background-color: #262730;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 1px solid #3a3b45;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 800;
        color: #ffffff;
        margin: 10px 0;
        font-family: 'Inter', sans-serif;
    }
    .metric-label {
        font-size: 1.1rem;
        color: #a0aabf;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
    }
    .metric-subtitle {
        font-size: 0.9rem;
        color: #6c757d;
        margin-top: 5px;
        font-family: 'Inter', sans-serif;
    }
</style>
""", unsafe_allow_html=True)

# ================= GOOGLE SHEETS FONKSİYONLARI =================
@st.cache_data(ttl=60)
def get_stok_data():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(credentials)
        sheet = client.open("Aksiyon_Guncel").worksheet("Stok")
        return sheet.get_all_values()
    except Exception as e:
        st.error(f"Google Sheets'e bağlanırken hata oluştu: {e}")
        return []

def get_bbx_data():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        credentials = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(credentials)
        sheet = client.open("Aksiyon_Guncel").worksheet("BBX")
        return sheet.get_all_values()
    except Exception as e:
        st.error(f"BBX Google Sheets'e bağlanırken hata: {e}")
        return []

# ================= BAŞLIK ALANI =================
if st.session_state.current_view == "ana_sayfa":
    st.markdown("<h1 class='main-title'>Aksiyon Raporu</h1>", unsafe_allow_html=True)
else:
    st.markdown("<h1 class='bbx-title'>🛒 BBX Fiyat & Satıcı Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p class='bbx-subtitle'>Trendyol ve Hepsiburada Buybox durumunuzu takip edin, müdahale gereken ürünleri alarm butonlarıyla anında dışa aktarın.</p>", unsafe_allow_html=True)

# ================= EKRAN YÖNLENDİRMELERİ =================

if st.session_state.current_view == "ana_sayfa":
    # ---------------------------------------------------------
    # EKRAN 1: AKSİYON RAPORU (ANA SAYFA - HERKESE AÇIK)
    # ---------------------------------------------------------
    
    # 1. Son Güncelleme Yazısı ve Hemen Altında Buton Konumu
    st.write(f"⏱️ Son Güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    # İSTEDİĞİN DEĞİŞİKLİK TAM OLARAK BURADA:
    if st.button("🔐 BBX Paneline Giriş Yap (Şifreli)", use_container_width=True):
        st.session_state.current_view = "bbx_paneli"
        st.rerun()
        
    st.markdown("---")

    data = get_stok_data()

    if data:
        headers = data[0]
        df = pd.DataFrame(data[1:], columns=headers)
        
        if "Önerilen Aksiyon" in df.columns:
            toplam_aksiyon = len(df[df["Önerilen Aksiyon"].str.strip() != ""])
            indirim_sayisi = len(df[df["Önerilen Aksiyon"].str.contains("Fiyat Düş", na=False)])
            zam_sayisi = len(df[df["Önerilen Aksiyon"].str.contains("Fiyat Artır", na=False)])
            stok_uyari = len(df[df["Önerilen Aksiyon"].str.contains("Stok Çek", na=False)])

            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Toplam Aksiyon Bekleyen</div><div class="metric-value" style="color: #4facfe;">{toplam_aksiyon}</div><div class="metric-subtitle">İncelenmesi gereken ürün</div></div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="metric-card"><div class="metric-label">İndirim Önerisi</div><div class="metric-value" style="color: #00f2fe;">{indirim_sayisi}</div><div class="metric-subtitle">Rakiplerin altına inmek için</div></div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Zam Önerisi</div><div class="metric-value" style="color: #ff9a9e;">{zam_sayisi}</div><div class="metric-subtitle">Kar marjını artırmak için</div></div>', unsafe_allow_html=True)
            with col4:
                st.markdown(f'<div class="metric-card"><div class="metric-label">Stok Tükendi</div><div class="metric-value" style="color: #fecfef;">{stok_uyari}</div><div class="metric-subtitle">Acil stok girişi gerekenler</div></div>', unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 📋 Detaylı Aksiyon Listesi")
            
            st.dataframe(df, use_container_width=True, height=600, hide_index=True)
        else:
            st.error("'Önerilen Aksiyon' sütunu bulunamadı. Lütfen Google Sheets dosyanızı kontrol edin.")
    else:
        st.warning("Veri bulunamadı. Lütfen Google Sheets bağlantınızı ve dosyanızı kontrol edin.")

elif st.session_state.current_view == "bbx_paneli":
    # ---------------------------------------------------------
    # EKRAN 2: BBX PANELİ (ŞİFRELİ ALAN)
    # ---------------------------------------------------------
    
    # BBX Panelindeyken de geri dönme butonunu en üste koyuyoruz ki kaybolmasın
    if st.button("🔙 Aksiyon Raporuna Geri Dön", use_container_width=True):
        st.session_state.current_view = "ana_sayfa"
        st.rerun()
        
    st.markdown("---")

    if not st.session_state.bbx_authenticated:
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.info("ℹ️ Bu alana erişim kısıtlanmıştır. Lütfen yönetici şifresini giriniz.")
            pwd = st.text_input("Giriş Şifresi:", type="password")
            if pwd == "mobese":
                st.session_state.bbx_authenticated = True
                st.success("✅ Şifre doğru! Giriş yapılıyor...")
                st.rerun()
            elif pwd:
                st.error("❌ Hatalı şifre!")
    else:
        raw_data = get_bbx_data()

        if raw_data:
            all_export_data = []
            ty_alarm_data = []
            hb_alarm_data = []
            
            html_table = """
            <style>
                .table-wrapper {
                    background-color: var(--background-color);
                    border-radius: 12px;
                    padding: 1px;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
                    overflow: hidden;
                    margin-top: 5px;
                    border: 1px solid var(--secondary-background-color);
                }
                .custom-table { width: 100%; border-collapse: collapse; font-family: 'Inter', sans-serif; font-size: 13px; color: var(--text-color); }
                .custom-table th, .custom-table td { border: 1px solid var(--secondary-background-color); padding: 12px 6px; text-align: center; vertical-align: middle; }
                .custom-table th { background-color: var(--secondary-background-color); color: var(--text-color); font-weight: 600; text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; }
                
                .urun-hucre { font-weight: 600; color: var(--text-color); }
                .sku-hucre { color: #0078ff !important; font-weight: 800; font-size: 14px; } 
                
                .pill-satici { background-color: var(--secondary-background-color); border: 1px solid rgba(128, 128, 128, 0.2); color: var(--text-color); border-radius: 20px; padding: 4px 12px; font-weight: 600; font-size: 12px; display: inline-block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 130px; }
                .pill-fiyat { background-color: rgba(0, 184, 76, 0.1); border: 1px solid rgba(0, 184, 76, 0.3); color: #00b84c; border-radius: 20px; padding: 4px 14px; font-weight: 800; font-size: 13px; display: inline-block; box-shadow: 0 2px 4px rgba(0, 184, 76, 0.1); }
                
                @keyframes blink-animation { 0% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(1.1); } 100% { opacity: 1; transform: scale(1); } }
                .status-dot { height: 14px; width: 14px; border-radius: 50%; display: inline-block; animation: blink-animation 1.5s infinite; }
                .dot-green { background-color: #00e676; box-shadow: 0 0 10px #00e676; }
                .dot-yellow { background-color: #ffea00; box-shadow: 0 0 10px #ffea00; }
                .dot-red { background-color: #ff1744; box-shadow: 0 0 10px #ff1744; }
                
                .no-border-bottom { border-bottom: none !important; padding-bottom: 2px !important; }
                .no-border-top { border-top: none !important; padding-top: 2px !important; }
                .product-divider { border-bottom: 2px solid var(--secondary-background-color) !important; }
                .custom-table tbody tr:hover td { background-color: var(--secondary-background-color); }
            </style>
            
            <div class="table-wrapper">
            <table class="custom-table">
                <thead>
                    <tr>
                        <th rowspan="2">Barkod</th>
                        <th rowspan="2">HB Kod</th>
                        <th rowspan="2">SKU</th>
                        <th rowspan="2">Alt Grup</th>
                        <th colspan="4" style="font-size: 14px; font-weight: 800;">TRENDYOL</th>
                        <th colspan="4" style="font-size: 14px; font-weight: 800;">HEPSİBURADA</th>
                    </tr>
                    <tr>
                        <th style="width: 45px;">Durum</th>
                        <th>1. Satıcı</th>
                        <th>2. Satıcı</th>
                        <th>3. Satıcı</th>
                        <th style="width: 45px;">Durum</th>
                        <th>1. Satıcı</th>
                        <th>2. Satıcı</th>
                        <th>3. Satıcı</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            for row in raw_data:
                while len(row) < 16: row.append("")
                barkod = str(row[0]).strip()
                sku = str(row[2]).strip()
                
                if "barkod" in barkod.lower() or "fiyat" in barkod.lower() or "satıcı" in barkod.lower(): continue
                if len("".join(row).strip()) < 3: continue
                    
                hb_kod = str(row[1]).strip() if row[1] else "-"
                alt_grup = str(row[3]).strip() if row[3] else "-"
                if not barkod: barkod = "-"
                if not sku: sku = "-"

                ty_raw_s1 = str(row[4]).strip().lower()
                ty_raw_s2 = str(row[6]).strip().lower()
                ty_raw_s3 = str(row[8]).strip().lower()
                
                hb_raw_s1 = str(row[10]).strip().lower()
                hb_raw_s2 = str(row[12]).strip().lower()
                hb_raw_s3 = str(row[14]).strip().lower()

                def is_ty_store(seller_name): return "trendyol" in seller_name or "braun shop" in seller_name
                ty_status_text = ""
                if is_ty_store(ty_raw_s1): 
                    ty_dot = "dot-green"
                    ty_status_text = "Sorun Yok (Yeşil)"
                elif is_ty_store(ty_raw_s2) or is_ty_store(ty_raw_s3): 
                    ty_dot = "dot-yellow"
                    ty_status_text = "Dikkat: Buybox 2. veya 3. Sırada (Sarı)"
                else: 
                    ty_dot = "dot-red"
                    ty_status_text = "Kritik: Buybox Kaybedildi (Kırmızı)"

                def is_hb_store(seller_name): return "hepsiburada" in seller_name or "braun shop" in seller_name
                hb_status_text = ""
                if is_hb_store(hb_raw_s1): 
                    hb_dot = "dot-green"
                    hb_status_text = "Sorun Yok (Yeşil)"
                elif is_hb_store(hb_raw_s2) or is_hb_store(hb_raw_s3): 
                    hb_dot = "dot-yellow"
                    hb_status_text = "Dikkat: Buybox 2. veya 3. Sırada (Sarı)"
                else: 
                    hb_dot = "dot-red"
                    hb_status_text = "Kritik: Buybox Kaybedildi (Kırmızı)"

                all_export_data.append({
                    "Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup,
                    "TY Durum": ty_status_text, "TY Satıcı 1": str(row[4]).strip(), "TY Fiyat 1": str(row[5]).strip(), "TY Satıcı 2": str(row[6]).strip(), "TY Fiyat 2": str(row[7]).strip(), "TY Satıcı 3": str(row[8]).strip(), "TY Fiyat 3": str(row[9]).strip(),
                    "HB Durum": hb_status_text, "HB Satıcı 1": str(row[10]).strip(), "HB Fiyat 1": str(row[11]).strip(), "HB Satıcı 2": str(row[12]).strip(), "HB Fiyat 2": str(row[13]).strip(), "HB Satıcı 3": str(row[14]).strip(), "HB Fiyat 3": str(row[15]).strip()
                })
                
                if ty_dot in ["dot-yellow", "dot-red"]:
                    ty_alarm_data.append({
                        "Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup, "Alarm Durumu": ty_status_text,
                        "TY Satıcı 1": str(row[4]).strip(), "TY Fiyat 1": str(row[5]).strip(), 
                        "TY Satıcı 2": str(row[6]).strip(), "TY Fiyat 2": str(row[7]).strip(), 
                        "TY Satıcı 3": str(row[8]).strip(), "TY Fiyat 3": str(row[9]).strip()
                    })

                if hb_dot in ["dot-yellow", "dot-red"]:
                    hb_alarm_data.append({
                        "Barkod": barkod, "HB Kod": hb_kod, "SKU": sku, "Alt Grup": alt_grup, "Alarm Durumu": hb_status_text,
                        "HB Satıcı 1": str(row[10]).strip(), "HB Fiyat 1": str(row[11]).strip(), 
                        "HB Satıcı 2": str(row[12]).strip(), "HB Fiyat 2": str(row[13]).strip(), 
                        "HB Satıcı 3": str(row[14]).strip(), "HB Fiyat 3": str(row[15]).strip()
                    })

                def get_pill_satici(val):
                    val = val.strip() if val else "-"
                    if val == "-" or val.lower() == "nan": return "-"
                    return f"<span class='pill-satici' title='{val}'>{val}</span>"

                def get_pill_fiyat(f):
                    f = f.strip() if f else "-"
                    if f != "-" and f.lower() != "nan":
                        val = f"{f} TL" if "TL" not in f else f
                        return f"<span class='pill-fiyat'>{val}</span>"
                    return "-"

                ty_s1, ty_f1 = get_pill_satici(row[4]), get_pill_fiyat(row[5])
                ty_s2, ty_f2 = get_pill_satici(row[6]), get_pill_fiyat(row[7])
                ty_s3, ty_f3 = get_pill_satici(row[8]), get_pill_fiyat(row[9])
                
                hb_s1, hb_f1 = get_pill_satici(row[10]), get_pill_fiyat(row[11])
                hb_s2, hb_f2 = get_pill_satici(row[12]), get_pill_fiyat(row[13])
                hb_s3, hb_f3 = get_pill_satici(row[14]), get_pill_fiyat(row[15])

                html_string = (
                    f"<tr><td rowspan='2' class='urun-hucre product-divider'>{barkod}</td><td rowspan='2' class='product-divider'>{hb_kod}</td><td rowspan='2' class='sku-hucre product-divider'>{sku}</td><td rowspan='2' class='product-divider'>{alt_grup}</td>"
                    f"<td rowspan='2' class='product-divider'><div class='status-dot {ty_dot}'></div></td><td class='no-border-bottom'>{ty_s1}</td><td class='no-border-bottom'>{ty_s2}</td><td class='no-border-bottom'>{ty_s3}</td>"
                    f"<td rowspan='2' class='product-divider'><div class='status-dot {hb_dot}'></div></td><td class='no-border-bottom'>{hb_s1}</td><td class='no-border-bottom'>{hb_s2}</td><td class='no-border-bottom'>{hb_s3}</td></tr>"
                    f"<tr><td class='no-border-top product-divider'>{ty_f1}</td><td class='no-border-top product-divider'>{ty_f2}</td><td class='no-border-top product-divider'>{ty_f3}</td><td class='no-border-top product-divider'>{hb_f1}</td><td class='no-border-top product-divider'>{hb_f2}</td><td class='no-border-top product-divider'>{hb_f3}</td></tr>"
                )
                html_table += html_string
                
            html_table += "</tbody></table></div>"
            
            buffer_all = io.BytesIO()
            with pd.ExcelWriter(buffer_all, engine='openpyxl') as w: pd.DataFrame(all_export_data).to_excel(w, index=False)
            
            buffer_ty = io.BytesIO()
            with pd.ExcelWriter(buffer_ty, engine='openpyxl') as w: pd.DataFrame(ty_alarm_data).to_excel(w, index=False)
                
            buffer_hb = io.BytesIO()
            with pd.ExcelWriter(buffer_hb, engine='openpyxl') as w: pd.DataFrame(hb_alarm_data).to_excel(w, index=False)

            col1, col2, col3 = st.columns([0.30, 0.35, 0.35])
            
            with col1:
                st.success(f"✅ {len(all_export_data)} ürün incelendi.")
                st.download_button("📥 Tüm Tabloyu İndir", buffer_all.getvalue(), file_name="Tum_Buybox_Analizi.xlsx", use_container_width=True)
                
            with col2:
                if len(ty_alarm_data) > 0:
                    st.error(f"⚠️ {len(ty_alarm_data)} üründe Trendyol Alarmı!")
                    st.download_button("🚨 Trendyol Alarm Aktar", buffer_ty.getvalue(), file_name="Trendyol_Alarm_Urunleri.xlsx", use_container_width=True)
                else:
                    st.success("✨ Trendyol Buybox Kusursuz!")
                    
            with col3:
                if len(hb_alarm_data) > 0:
                    st.error(f"⚠️ {len(hb_alarm_data)} üründe Hepsiburada Alarmı!")
                    st.download_button("🚨 Hepsiburada Alarm Aktar", buffer_hb.getvalue(), file_name="Hepsiburada_Alarm_Urunleri.xlsx", use_container_width=True)
                else:
                    st.success("✨ Hepsiburada Buybox Kusursuz!")

            clean_html = html_table.replace('\n', '')
            st.markdown(clean_html, unsafe_allow_html=True)
        else:
            st.error("❌ Google Sheets tablosunda veri bulunamadı veya satırlar tamamen boş!")
