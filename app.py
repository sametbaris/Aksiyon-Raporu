import streamlit as st
import pandas as pd
import requests
import time
import concurrent.futures
from datetime import datetime
import base64
import re

# BBX İÇİN EKLENEN KÜTÜPHANELER
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

# ================= ORİJİNAL ANA SAYFA FONKSİYONLARI =================
def fetch_product_link(barcode, is_hepsiburada=False):
    """Verilen barkod için Trendyol veya Hepsiburada'da arama yapıp ilk ürünün linkini döndürür."""
    if is_hepsiburada:
        search_url = f"https://www.hepsiburada.com/ara?q={barcode}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.hepsiburada.com/"
        }
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                html_content = response.text
                match = re.search(r'<a[^>]+href="(/[^"]+-p-[^"]+)"[^>]*>', html_content)
                if match:
                    product_path = match.group(1)
                    return f"https://www.hepsiburada.com{product_path}"
                
                # Alternatif arama (merchant-product)
                match2 = re.search(r'<a[^>]+href="(/magaza/[^"]+)"[^>]*>', html_content)
                if match2:
                    product_path = match2.group(1)
                    return f"https://www.hepsiburada.com{product_path}"
                    
        except Exception as e:
            pass
        return ""
        
    else:
        search_url = f"https://public-mdc.trendyol.com/discovery-web-searchgw-service/v2/api/infinite-scroll/sr?q={barcode}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.trendyol.com",
            "Referer": f"https://www.trendyol.com/sr?q={barcode}"
        }
        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("result", {}).get("products"):
                    product = data["result"]["products"][0]
                    return f"https://www.trendyol.com{product['url']}"
        except Exception as e:
            pass
        return ""

def process_links(df):
    """Sadece linki eksik olan barkodlar için link çekme işlemini yapar."""
    if 'TY Link' not in df.columns:
        df['TY Link'] = ""
    if 'HB Link' not in df.columns:
        df['HB Link'] = ""
        
    missing_ty = df[df['TY Link'].isna() | (df['TY Link'] == '')]
    missing_hb = df[df['HB Link'].isna() | (df['HB Link'] == '')]
    
    total_missing = len(missing_ty) + len(missing_hb)
    
    if total_missing == 0:
        return df, 0
        
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    processed = 0
    
    # Trendyol linklerini çek
    if len(missing_ty) > 0:
        status_text.text(f"Trendyol linkleri aranıyor... (0/{len(missing_ty)})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {executor.submit(fetch_product_link, row['Barkod'], False): idx 
                           for idx, row in missing_ty.iterrows()}
            
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    link = future.result()
                    if link:
                        df.at[idx, 'TY Link'] = link
                except Exception:
                    pass
                processed += 1
                progress_bar.progress(processed / total_missing)
                status_text.text(f"Linkler aranıyor... ({processed}/{total_missing})")
                time.sleep(0.1)

    # Hepsiburada linklerini çek
    if len(missing_hb) > 0:
        status_text.text(f"Hepsiburada linkleri aranıyor... (0/{len(missing_hb)})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_idx = {executor.submit(fetch_product_link, row['Barkod'], True): idx 
                           for idx, row in missing_hb.iterrows()}
            
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    link = future.result()
                    if link:
                        df.at[idx, 'HB Link'] = link
                except Exception:
                    pass
                processed += 1
                progress_bar.progress(processed / total_missing)
                status_text.text(f"Linkler aranıyor... ({processed}/{total_missing})")
                time.sleep(0.5)

    progress_bar.empty()
    status_text.empty()
    
    return df, processed

def get_table_download_link(df, filename="aksiyon_raporu_guncel.csv"):
    """DataFrame'i CSV olarak indirmek için link oluşturur."""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}" class="download-button">Tüm Tabloyu İndir (CSV)</a>'
    return href

@st.cache_data(ttl=600)
def load_data(sheet_id, sheet_name="Stok"):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
        return None

# ================= BBX PANELİ İÇİN FONKSİYON =================
def get_bbx_data_from_sheets():
    try:
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        credentials = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(credentials)
        sheet = client.open("Aksiyon_Guncel").worksheet("BBX")
        return sheet.get_all_values()
    except Exception as e:
        st.error(f"Google Sheets'e bağlanırken hata: {e}")
        return []

# ================= EKRAN YÖNLENDİRMELERİ =================

if st.session_state.current_view == "ana_sayfa":
    # ---------------------------------------------------------
    # EKRAN 1: AKSİYON RAPORU (ORİJİNAL KODUN HİÇ DEĞİŞTİRİLMEDİ)
    # ---------------------------------------------------------
    st.markdown("""
    <style>
        /* Ana Başlık */
        .main-title {
            text-align: left;
            background: linear-gradient(90deg, #f8f9fa, #e9ecef);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 800;
            font-size: 2.5rem;
            margin-bottom: 0;
            padding-bottom: 0;
        }

        /* Metrik Kartları */
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
        }
        .metric-label {
            font-size: 1.1rem;
            color: #a0aabf;
            font-weight: 600;
        }
        .metric-subtitle {
            font-size: 0.9rem;
            color: #6c757d;
            margin-top: 5px;
        }

        /* DataFrame Özelleştirme */
        .dataframe {
            font-size: 12px !important;
        }
        
        /* Butonlar */
        .stButton>button {
            width: 100%;
            border-radius: 5px;
            font-weight: bold;
        }
        .download-button {
            display: inline-block;
            padding: 0.5em 1em;
            color: #ffffff;
            background-color: #4facfe;
            border-radius: 5px;
            text-decoration: none;
            font-weight: bold;
            text-align: center;
            width: 100%;
            margin-top: 10px;
        }
        .download-button:hover {
            background-color: #00f2fe;
            color: #ffffff;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<h1 class='main-title'>Aksiyon Raporu</h1>", unsafe_allow_html=True)
    st.write(f"Son Güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    
    # İŞTE BBX BUTONU! SADECE BURAYA EKLENDİ!
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔐 BBX Paneline Giriş Yap (Şifreli)", use_container_width=True):
        st.session_state.current_view = "bbx_paneli"
        st.rerun()
    st.markdown("---")

    SHEET_ID = "142yZJ90wUoU9YF48S9N2-T9_6lZg6iC1w9EAS7l9XW4"
    df = load_data(SHEET_ID)

    if df is not None:
        
        with st.sidebar:
            st.header("🔗 Link İşlemleri")
            st.write("Eksik olan Trendyol ve Hepsiburada linklerini otomatik çekin.")
            
            if st.button("Linkleri Çek", type="primary"):
                with st.spinner("Linkler aranıyor..."):
                    updated_df, count = process_links(df)
                    if count > 0:
                        st.success(f"Başarıyla {count} yeni link bulundu!")
                        st.session_state['updated_df'] = updated_df
                    else:
                        st.info("Tüm linkler zaten mevcut veya bulunamadı.")
            
            if 'updated_df' in st.session_state:
                st.markdown(get_table_download_link(st.session_state['updated_df'], "aksiyon_raporu_linkli.csv"), unsafe_allow_html=True)
                
            st.markdown("---")
            st.header("Filtreler")

        if 'Önerilen Aksiyon' in df.columns:
            toplam_aksiyon = len(df[df['Önerilen Aksiyon'].str.strip() != ''])
            indirim_sayisi = len(df[df['Önerilen Aksiyon'].str.contains('Fiyat Düş', na=False)])
            zam_sayisi = len(df[df['Önerilen Aksiyon'].str.contains('Fiyat Artır', na=False)])
            stok_uyari = len(df[df['Önerilen Aksiyon'].str.contains('Stok Çek', na=False)])

            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">Toplam Aksiyon Bekleyen</div>
                        <div class="metric-value" style="color: #4facfe;">{toplam_aksiyon}</div>
                        <div class="metric-subtitle">İncelenmesi gereken ürün</div>
                    </div>
                """, unsafe_allow_html=True)
                
            with col2:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">İndirim Önerisi</div>
                        <div class="metric-value" style="color: #00f2fe;">{indirim_sayisi}</div>
                        <div class="metric-subtitle">Rakiplerin altına inmek için</div>
                    </div>
                """, unsafe_allow_html=True)
                
            with col3:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">Zam Önerisi</div>
                        <div class="metric-value" style="color: #ff9a9e;">{zam_sayisi}</div>
                        <div class="metric-subtitle">Kar marjını artırmak için</div>
                    </div>
                """, unsafe_allow_html=True)
                
            with col4:
                st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">Stok Tükendi</div>
                        <div class="metric-value" style="color: #fecfef;">{stok_uyari}</div>
                        <div class="metric-subtitle">Acil stok girişi gerekenler</div>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            if 'updated_df' in st.session_state:
                df = st.session_state['updated_df']

            search_term = st.sidebar.text_input("🔍 SKU veya Barkod Ara:")
            alt_grup_filter = st.sidebar.multiselect("Alt Grup Seçin:", options=sorted(df['Alt Grup'].dropna().unique()) if 'Alt Grup' in df.columns else [])
            aksiyon_filter = st.sidebar.multiselect("Aksiyon Tipi:", options=sorted(df['Önerilen Aksiyon'].dropna().unique()))

            filtered_df = df.copy()
            if search_term:
                filtered_df = filtered_df[filtered_df.astype(str).apply(lambda x: x.str.contains(search_term, case=False, na=False)).any(axis=1)]
            if alt_grup_filter:
                filtered_df = filtered_df[filtered_df['Alt Grup'].isin(alt_grup_filter)]
            if aksiyon_filter:
                filtered_df = filtered_df[filtered_df['Önerilen Aksiyon'].isin(aksiyon_filter)]

            tab1, tab2 = st.tabs(["📋 Detaylı Aksiyon Listesi", "📈 Trend Analizi (Yakında)"])

            with tab1:
                st.dataframe(
                    filtered_df,
                    use_container_width=True,
                    height=600,
                    hide_index=True
                )
                
                final_df = filtered_df if (search_term or alt_grup_filter or aksiyon_filter) else df
                st.markdown(get_table_download_link(final_df), unsafe_allow_html=True)

            with tab2:
                st.info("Trend analizi ve grafikler bu sekmede yer alacaktır.")
                
        else:
            st.error("'Önerilen Aksiyon' sütunu bulunamadı. Lütfen Google Sheets dosyasındaki sütun isimlerini kontrol edin.")
            st.dataframe(df.head())

elif st.session_state.current_view == "bbx_paneli":
    # ---------------------------------------------------------
    # EKRAN 2: BBX PANELİ (ŞİFRELİ ALAN)
    # ---------------------------------------------------------
    st.markdown("""
    <style>
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
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<h1 class='bbx-title'>🛒 BBX Fiyat & Satıcı Analizi</h1>", unsafe_allow_html=True)
    st.markdown("<p class='bbx-subtitle'>Trendyol ve Hepsiburada Buybox durumunuzu takip edin, müdahale gereken ürünleri alarm butonlarıyla anında dışa aktarın.</p>", unsafe_allow_html=True)
    
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
        raw_data = get_bbx_data_from_sheets()

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
