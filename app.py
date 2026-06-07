import streamlit as st
import feedparser
from openai import OpenAI
import json
from datetime import datetime

# 1. Konfiguracja strony i wyglądu (Szata graficzna)
st.set_page_config(
    page_title="Energy Regulatory Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Customowy CSS dla ulepszenia wyglądu kart
st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #2e7d32;
        margin-bottom: 15px;
    }
    .high-risk { border-left-color: #d32f2f; }
    .medium-risk { border-left-color: #f57c00; }
    .low-risk { border-left-color: #388e3c; }
    </style>
""", unsafe_allowed_html=True)

# 2. Inicjalizacja połączeń (Baza danych i LLM)
# Streamlit automatycznie pobierze te dane z Secretów w chmurze
conn = st.connection("postgresql", type="sql")
client = OpenAI(
    base_url="https://api.groq.com/openai/v1", # Przykładowy darmowy/tani dostawca (np. Groq dla Llama 3)
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
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        return {"score": 1, "reasoning": "Błąd analizy LLM", "summary_pl": summary}

def fetch_and_update_news():
    """Pobiera świeże dane z RSS i procesuje nowości przez LLM"""
    # Przykładowy ogólny feed (w docelowym rozwiązaniu wstawiasz np. RSS z ACER / KE)
    feed_url = "[https://ec.europa.eu/commission/presscorner/api/rss?portal=1018&language=en](https://ec.europa.eu/commission/presscorner/api/rss?portal=1018&language=en)"
    feed = feedparser.parse(feed_url)
    
    new_records_count = 0
    
    for entry in feed.entries[:10]: # Sprawdzamy top 10 ostatnich wpisów
        title = entry.title
        url = entry.link
        
        # Sprawdzenie czy artykuł już istnieje w bazie
        existing = conn.query(f"SELECT id FROM energy_news WHERE title = :title", params={"title": title})
        if len(existing) == 0:
            # Sukces - mamy nowy artykuł. Analizujemy go przez LLM
            raw_summary = entry.get('summary', '')
            analysis = analyze_with_llm(title, raw_summary)
            
            # Zapis do bazy danych
            with conn.session as session:
                session.execute(
                    """
                    INSERT INTO energy_news (title, url, published_date, summary, relevance_score, impact_reasoning)
                    VALUES (:title, :url, :date, :summary, :score, :reasoning)
                    """,
                    {
                        "title": title, "url": url, "date": datetime.now(),
                        "summary": analysis["summary_pl"], "score": analysis["score"],
                        "reasoning": analysis["reasoning"]
                    }
                )
                session.commit()
            new_records_count += 1
            
    return new_records_count

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
            st.rerun()
            
    st.write("---")
    min_score = st.slider("Minimalna istotność wpisu (1-10)", 1, 10, 4)

# Główny widok danych
st.markdown("### Ostatnie istotne zmiany regulacyjne")

# Pobranie danych z bazy z filtrowaniem poziomu istotności
df = conn.query(
    "SELECT * FROM energy_news WHERE relevance_score >= :min_score ORDER BY published_date DESC", 
    params={"min_score": min_score}
)

if df.empty:
    st.info("Brak wiadomości spełniających kryteria filtrowania. Kliknij przycisk odświeżenia w panelu bocznym.")
else:
    for index, row in df.iterrows():
        # Dynamiczne dobieranie klasy CSS na podstawie punktacji
        score = row['relevance_score']
        if score >= 7:
            card_class = "metric-card high-risk"
            badge = f"🔴 Krytyczny ({score}/10)"
        elif score >= 5:
            card_class = "metric-card medium-risk"
            badge = f"🟠 Średni ({score}/10)"
        else:
            card_class = "metric-card low-risk"
            badge = f"🟢 Niski ({score}/10)"
            
        # Renderowanie pięknej karty za pomocą HTML wstrzykniętego do Streamlit
        st.markdown(f"""
            <div class="{card_class}">
                <h4>{row['title']}</h4>
                <p style="font-size: 0.9em; color: #666;"><strong>Status wpływu:</strong> {badge}</p>
                <p><strong>Podsumowanie zmian:</strong> {row['summary']}</p>
                <p style="background-color: #e8f5e9; padding: 10px; border-radius: 5px;">
                    <strong>Wpływ na modele cenowe:</strong> {row['impact_reasoning']}
                </p>
                <a href="{row['url']}" target="_blank">👉 Przejdź do oficjalnego źródła</a>
            </div>
        """, unsafe_allowed_html=True)