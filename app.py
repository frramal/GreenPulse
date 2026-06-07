import streamlit as st
import feedparser
from openai import OpenAI
import json
import requests
from datetime import datetime, timedelta
from sqlalchemy import text
import re
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

# 1. Konfiguracja strony i wyglądu (Szata graficzna)
st.set_page_config(
    page_title="Energy Regulatory Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Customowy CSS dla ulepszenia wyglądu kart (Paleta: Czarny, Biały, Zielony, Miętowy, Żółty)
st.markdown("""
    <style>
    /* Główny kontener karty - czarne tło, biały tekst */
    .metric-card {
        background-color: #111111 !important; 
        color: #ffffff !important;
        border-radius: 12px;
        padding: 20px;
        border: 1px solid #222222;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
    }
    
    /* Wymuszenie białego koloru dla tytułów wewnątrz kart */
    .metric-card h4 {
        color: #ffffff !important;
        margin-top: 0 !important;
        font-weight: 600 !important;
    }
    
    /* Wymuszenie jasnego tekstu dla opisów */
    .metric-card p {
        color: #e0e0e0 !important;
    }
    
    /* Klasy kolorystyczne dla poziomów istotności (Boczny pasek karty) */
    .high-risk { border-left: 6px solid #ffd54f !important; }   /* Żółty */
    .medium-risk { border-left: 6px solid #69f0ae !important; } /* Miętowy */
    .low-risk { border-left: 6px solid #2e7d32 !important; }    /* Zielony */
    
    /* Specjalne okienko na uzasadnienie wpływu modelowego */
    .reasoning-box {
        background-color: #1a1a1a !important;
        color: #69f0ae !important; /* Tekst w kolorze miętowym dla wyróżnienia */
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #333333;
        margin-top: 12px;
    }
    
    /* Linki wewnątrz karty */
    .metric-card a {
        color: #69f0ae !important; /* Miętowy link */
        text-decoration: none !important;
        font-weight: bold;
    }
    .metric-card a:hover {
        color: #ffd54f !important; /* Zmiana na żółty po najechaniu */
        text-decoration: underline !important;
    }
    </style>
""", unsafe_allow_html=True)

# 2. Inicjalizacja połączeń (Baza danych i LLM)
conn = st.connection(
    "postgresql", 
    type="sql",
    kwargs={
        "pool_pre_ping": True,  # Automatyczne odnawianie zerwanych połączeń z Neon
        "pool_recycle": 300,    # Resetowanie połączenia co 5 minut
        "connect_args": {
            "sslmode": "require" # Wymuszenie bezpiecznego tunelu SSL
        }
    }
)
client = OpenAI(
    base_url="https://api.groq.com/openai/v1", 
    api_key=st.secrets["GROQ_API_KEY"]
)

def analyze_with_llm(title, summary):
    """Wysyła tekst do LLM w celu strukturyzacji i oceny istotności"""
    prompt = f"""
    Przeanalizuj poniższy komunikat z europejskiego rynku energii pod kątem modelowania cen zielonych kontraktów (PPA, gwarancje pochodzenia, ryzyko profilu).
    Tytuł: {title}
    Opis: {summary}
    
    Zwróć WYŁĄCZNIE czysty obiekt JSON (bez markdownu ```json) o strukturze:
    {{"score": int, "reasoning": "krótkie uzasadnienie po polsku", "summary_pl": "zwięzłe podsumowanie zmian po polsku"}}
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        
        # Wyciąganie JSON-a w razie, gdyby LLM dodał markdown
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
            
        return json.loads(content)
    except Exception as e:
        print(f"Błąd analizy LLM: {e}")
        return {"score": 1, "reasoning": f"Błąd analizy LLM: {str(e)[:50]}", "summary_pl": summary}

def fetch_and_update_news():
    """Pobiera świeże dane z RSS, omija blokady, analizuje przez LLM i zapisuje do bazy danych"""
    feed_urls = [
        "https://cleantechnica.com/feed/",
        "https://www.renewableenergyworld.com/feed/",
        "https://www.energy-storage.news/feed/"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    new_records_count = 0
    
    for feed_url in feed_urls:
        st.info(f"🛰️ Nawiązywanie połączenia z kanałem: {feed_url}")
        
        try:
            response = requests.get(feed_url, headers=headers, timeout=10)
            feed = feedparser.parse(response.text)
        except Exception as e:
            st.error(f"❌ Błąd pobierania danych z {feed_url}: {e}")
            continue
        
        if len(feed.entries) == 0:
            st.warning(f"⚠️ Kanał RSS {feed_url} nie zwrócił żadnych artykułów.")
            continue
            
        for i, entry in enumerate(feed.entries[:15]): 
            title = entry.title
            url = entry.link
            
            # Próba wydobycia daty publikacji
            pub_date = datetime.now()
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                from time import mktime
                pub_date = datetime.fromtimestamp(mktime(entry.published_parsed))
            elif hasattr(entry, 'published'):
                try:
                    from email.utils import parsedate_to_datetime
                    pub_date = parsedate_to_datetime(entry.published)
                    pub_date = pub_date.replace(tzinfo=None) 
                except:
                    pass
                    
            st.toast(f"🔍 Wpis {i+1}/15 z {feed_url.split('/')[2]}: {title[:30]}...", icon="🔍")
            
            existing = conn.query("SELECT id FROM energy_news WHERE title = :title", params={"title": title}, ttl=0)
            
            if len(existing) == 0:
                st.toast(f"🧠 Znaleziono nowość! Analiza: {title[:30]}...", icon="🧠")
                raw_summary = entry.get('summary', '')
                analysis = analyze_with_llm(title, raw_summary)
                
                st.toast(f"💾 Zapisano wynik! (Istotność: {analysis['score']}/10)", icon="💾")
                
                with conn.session as session:
                    session.execute(
                        text("""
                        INSERT INTO energy_news (title, url, published_date, summary, relevance_score, impact_reasoning)
                        VALUES (:title, :url, :date, :summary, :score, :reasoning)
                        """),
                        {
                            "title": title, "url": url, "date": pub_date,
                            "summary": analysis["summary_pl"], "score": analysis["score"],
                            "reasoning": analysis["reasoning"]
                        }
                    )
                    session.commit()
                new_records_count += 1
                
    return new_records_count

def generate_report_from_df(filtered_df):
    if filtered_df.empty:
        return "Brak danych do wygenerowania raportu."
        
    prompt = "Wygeneruj profesjonalny raport podsumowujący najnowsze wydarzenia z rynku energii na podstawie poniższych wiadomości:\n\n"
    for _, row in filtered_df.head(15).iterrows():
        prompt += f"- {row['title']}: {row['summary']}\n"
    
    prompt += "\nNapisz to w formie 2-3 zwięzłych akapitów. Wyróżnij najważniejsze trendy i ryzyka rynkowe. WAŻNE: Nie umieszczaj absolutnie żadnych prognoz, przewidywań ani spekulacji na przyszłość. Skup się wyłącznie na suchych faktach z dostarczonych wiadomości. Używaj formatowania markdown. Język polski."
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Błąd generowania raportu: {e}"

def generate_network_graph(df):
    prompt = "Przeanalizuj poniższe wiadomości i wyodrębnij maksymalnie 20 kluczowych powiązań między podmiotami.\n"
    prompt += "Zwróć wynik WYŁĄCZNIE jako JSON w formacie tablicy: [{\"source\": \"Nazwa A\", \"source_type\": \"Firma/Kraj/Technologia/Regulacja\", \"target\": \"Nazwa B\", \"target_type\": \"Firma/Kraj/Technologia/Regulacja\", \"label\": \"Krótki opis relacji\"}]. \n\nWiadomości:\n"
    for _, row in df.head(15).iterrows():
        prompt += f"- {row['title']}\n"
        
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            content = json_match.group(0)
        edges = json.loads(content)
        
        net_graph = Network(height='600px', width='100%', bgcolor='#111111', font_color='white')
        
        node_degrees = {}
        for edge in edges:
            node_degrees[edge.get("source")] = node_degrees.get(edge.get("source"), 0) + 1
            node_degrees[edge.get("target")] = node_degrees.get(edge.get("target"), 0) + 1
            
        color_map = {
            "Firma": "#ffd54f",
            "Kraj": "#69f0ae",
            "Technologia": "#4fc3f7",
            "Regulacja": "#ff8a65"
        }
        
        for edge in edges:
            src = edge.get("source")
            src_type = edge.get("source_type", "Inne")
            tgt = edge.get("target")
            tgt_type = edge.get("target_type", "Inne")
            lbl = edge.get("label", "")
            
            if src and tgt:
                src_size = 10 + (node_degrees.get(src, 1) * 4)
                tgt_size = 10 + (node_degrees.get(tgt, 1) * 4)
                
                net_graph.add_node(src, label=src, title=f"Typ: {src_type}", color=color_map.get(src_type, "#e0e0e0"), size=src_size)
                net_graph.add_node(tgt, label=tgt, title=f"Typ: {tgt_type}", color=color_map.get(tgt_type, "#e0e0e0"), size=tgt_size)
                net_graph.add_edge(src, tgt, title=lbl, color='#555555')
        
        net_graph.repulsion(node_distance=150, spring_length=200)
        
        import tempfile
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        net_graph.save_graph(tmp_file.name)
        return tmp_file.name
    except Exception as e:
        st.error(f"Błąd analizy grafu: {e}")
        return None

# --- INTERFEJS UŻYTKOWNIKA ---

st.title("⚡ Europejskie Regulacje Energetyczne")
st.subheader("Inteligentny asystent modelowania zielonych kontraktów")

# Sidebar - Sterowanie i Filtry
with st.sidebar:
    st.header("Zarządzanie agentem")
    if st.button("🔄 Uruchom skaner (Pobierz nowości)", type="primary"):
        with st.spinner("Agent przeszukuje źródła i analizuje teksty..."):
            added = fetch_and_update_news()
            st.success(f"Skanowanie zakończone! Dodano nowych wpisów: {added}")
            
    st.write("---")
    
    st.header("Filtry Danych i Raporty")
    min_score = st.slider("Minimalna istotność wpisu (1-10)", 1, 10, 4)
    
    default_start = datetime.now().date() - timedelta(days=7)
    default_end = datetime.now().date()
    date_range = st.date_input("Zakres dat publikacji", (default_start, default_end))
    
if len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = default_start, default_end

# Główne pobranie danych z bazy na podstawie filtrów z panelu bocznego
df = conn.query(
    "SELECT * FROM energy_news WHERE relevance_score >= :min_score AND DATE(published_date) >= :start_date AND DATE(published_date) <= :end_date ORDER BY published_date DESC LIMIT 50", 
    params={"min_score": min_score, "start_date": start_date, "end_date": end_date},
    ttl=0
)

with st.sidebar:
    st.write("---")
    st.write("Na podstawie powyższych filtrów możesz wygenerować inteligentne podsumowanie dla widocznych wyników.")
    if st.button("📝 Generuj Raport dla filtrów"):
        with st.spinner("LLM syntetyzuje raport z odfiltrowanych wiadomości..."):
            raport = generate_report_from_df(df)
            st.session_state['daily_report'] = raport

# Wyświetlanie raportu jeśli istnieje
if 'daily_report' in st.session_state:
    st.info(f"📊 **Raport Podsumowujący** (wygenerowano dla {len(df)} odfiltrowanych wyników)")
    st.markdown(st.session_state['daily_report'])
    if st.button("Ukryj raport"):
        del st.session_state['daily_report']
        st.rerun()

# Zakładki
tab1, tab2 = st.tabs(["📰 Wiadomości", "🕸️ Analityka (Graf powiązań)"])

with tab1:
    st.markdown("### Ostatnie istotne zmiany regulacyjne")
    if df.empty:
        st.info("Brak wiadomości spełniających kryteria filtrowania. Kliknij przycisk odświeżenia w panelu bocznym.")
    else:
        for index, row in df.iterrows():
            score = row['relevance_score']
            # Formatowanie daty, obsługa None lub różnego typu
            pub_date_str = "Brak daty"
            if row['published_date']:
                try:
                    pub_date_str = row['published_date'].strftime('%Y-%m-%d %H:%M')
                except:
                    pub_date_str = str(row['published_date'])
            
            if score >= 7:
                card_class = "metric-card high-risk"
                badge = "💛 Krytyczny"
            elif score >= 5:
                card_class = "metric-card medium-risk"
                badge = "💚 Średni"
            else:
                card_class = "metric-card low-risk"
                badge = "🌲 Niski"
                
            st.markdown(f"""
                <div class="{card_class}">
                    <h4>{row['title']}</h4>
                    <p style="font-size: 0.9em; color: #aaaaaa !important; margin-bottom: 10px;">
                        <strong>Data:</strong> {pub_date_str} | <strong>Status wpływu:</strong> {badge} ({score}/10)
                    </p>
                    <p><strong>Podsumowanie zmian:</strong> {row['summary']}</p>
                    <div class="reasoning-box">
                        <strong>📊 Wpływ na modele cenowe:</strong> {row['impact_reasoning']}
                    </div>
                    <br>
                    <a href="{row['url']}" target="_blank">👉 Przejdź do oficjalnego źródła</a>
                </div>
            """, unsafe_allow_html=True)

with tab2:
    st.markdown("### Wizualizacja powiązań z ostatnich wydarzeń")
    st.write("Agent sztucznej inteligencji analizuje ostatnie wiadomości, aby znaleźć ukryte relacje pomiędzy firmami, technologiami i krajami.")
    
    if st.button("Analizuj powiązania i generuj graf"):
        if not df.empty:
            with st.spinner("Budowanie grafu powiązań z użyciem LLM... To może chwilę potrwać."):
                html_file_path = generate_network_graph(df)
                if html_file_path:
                    st.markdown("""
                    **Legenda:** 
                    <span style="color:#ffd54f">🟡 Firma</span> | 
                    <span style="color:#69f0ae">🟢 Kraj</span> | 
                    <span style="color:#4fc3f7">🔵 Technologia</span> | 
                    <span style="color:#ff8a65">🟠 Regulacja</span> |
                    ⚪ Inne
                    """, unsafe_allow_html=True)
                    with open(html_file_path, 'r', encoding='utf-8') as f:
                        html_data = f.read()
                    components.html(html_data, height=650, scrolling=True)
        else:
            st.warning("Brak danych do analizy.")