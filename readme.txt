# ⚡ GreenPulse: Energy Regulatory Intelligence Agent

**GreenPulse** to inteligentny agent stworzony do automatycznego monitorowania, strukturyzacji i analizy europejskich regulacji energetycznych pod kątem modelowania cen zielonych kontraktów (cPPA/vPPA), ryzyka profilu (*profile risk*) oraz zjawiska kanibalizacji cen OZE.

Projekt automatyzuje proces śledzenia dynamicznych zmian prawnych (np. decyzji ACER, dyrektyw RED III, wytycznych REMIT II), odcinając szum informacyjny i dostarczając skondensowane, techniczne wnioski bezpośrednio do interaktywnego panelu analitycznego.

---

## 🚀 Kluczowe Funkcje

*   **Zautomatyzowana Agregacja Danych:** Pobieranie najnowszych komunikatów z oficjalnych unijnych źródeł regulacyjnych (Komisja Europejska, ACER, ENTSO-E).
*   **Semantyczna Analiza LLM:** Wykorzystanie zaawansowanych modeli językowych (np. Llama 3) z wymuszoną strukturą danych (*Structured Outputs* JSON) do oceny istotności komunikatów rynkowych w skali 1-10.
*   **Analityczny Dashboard:** Nowoczesny, responsywny interfejs użytkownika stworzony w Streamlit, umożliwiający dynamiczne filtrowanie wiadomości według poziomu wpływu regulacyjnego.
*   **Persistent Data Storage:** Integracja z chmurową bazą danych PostgreSQL (Neon.tech) gwarantująca deduplikację rekordów i optymalizację kosztów API.

---

## 🛠️ Architektura Technologiczna

*   **Backend:** Python, `feedparser`, `requests`
*   **AI/LLM Engine:** Groq API / OpenAI SDK (`Llama-3-70b`)
*   **Frontend / UI:** Streamlit
*   **Database:** PostgreSQL (Hosted on Neon.tech / Supabase)
*   **Hosting:** Streamlit Community Cloud

---

## 📦 Jak uruchomić projekt lokalnie

1. **Sklonuj repozytorium:**
```bash
   git clone [https://github.com/TWOJA_NAZWA_UZYTKOWNIKA/GreenPulse.git](https://github.com/TWOJA_NAZWA_UZYTKOWNIKA/GreenPulse.git)
   cd GreenPulse