# Google API Key Hunter & Validator

Zbiór narzędzi do ekstrakcji i weryfikacji kluczy Google API z plików APK, AAB, XAPK oraz APKM.

## 🛠 Narzędzia

W repozytorium znajdują się 4 skrypty Python, o różnym stopniu zaawansowania:

### 1. [apk.py](file:///home/daniel/pro/google-api-key-hack/apk.py)
Minimalistyczny skrypt do prostej ekstrakcji potencjalnych kluczy przy użyciu wyrażeń regularnych. Traktuje pakiety `.apkm` jak archiwa ZIP i przeszukuje ich zawartość.

### 2. [apk.test.py](file:///home/daniel/pro/google-api-key-hack/apk.test.py)
Rozszerzona wersja, która po znalezieniu kluczy automatycznie testuje ich ważność, wysyłając proste zapytanie do `Places API (New)`. Wyświetla status odpowiedzi i jej fragment.

### 3. [apk.all.py](file:///home/daniel/pro/google-api-key-hack/apk.all.py)
Narzędzie do kompleksowej weryfikacji kluczy. Testuje każdy znaleziony klucz pod kątem wielu endpointów:
- Places API (New)
- Legacy Places TextSearch
- Legacy Places Nearby
- Legacy Places Details

### 4. [apk.grok.py](file:///home/daniel/pro/google-api-key-hack/apk.grok.py)
Najbardziej zaawansowane narzędzie ("2025 Edition"):
- **Wielowątkowość**: Szybkie testowanie dużej liczby kluczy.
- **Inteligentna analiza**: Rozpoznaje konkretne powody błędów (wyłączone API, brak podpiętej karty płatniczej, restrykcje IP/Referer, wygaśnięcie klucza).
- **Obsługa wielu formatów**: Automatycznie dekompresuje zagnieżdżone APK w plikach XAPK/APKM.
- **Wykrywanie "High Value Keys"**: Oznacza klucze, które mają aktywnych więcej niż 3 usługi.
- **Kolorowy interfejs**: Wykorzystuje `colorama` do czytelnej prezentacji wyników w terminalu.

### 5. [apk.scan.py](file:///home/daniel/pro/google-api-key-hack/apk.scan.py)
Automatyczny skaner folderu `apps/` zintegrowany z MongoDB:
- **Diferencjalne skanowanie**: Oblicza hash SHA256 każdego pliku i skanuje tylko te, których nie ma jeszcze w bazie.
- **Baza MongoDB**: Przechowuje wyniki testów, hashe plików i metadane.
- **Integracja**: Wykorzystuje logikę z `apk_grok.py` (dawniej `apk.grok.py`).

### 6. [apk_getter.py](file:///home/daniel/pro/google-api-key-hack/apk_getter.py)
Automatyczny pobieracz nowych aplikacji z serwisu Aptoide:
- **Discovery**: Pobiera listę najpopularniejszych aplikacji (trending).
- **Automatyzacja**: Pobiera pliki APK bezpośrednio do katalogu `apps/`.
- **Inteligentne unikanie duplikatów**: Nie pobiera plików, które już istnieją w lokalnym folderze.

## 🗄️ Baza Danych MongoDB
...
## 📋 Przykładowe użycie

Pobieranie 5 nowych trendujących aplikacji:
```bash
python apk_getter.py --limit 5
```

Automatyczne skanowanie całego folderu `apps/` i zapis do bazy:
```bash
python apk.scan.py
```

Skanowanie z zapisem "cennych" kluczy:
```bash
python apk_grok.py /sciezka/do/apk --save-good
```

## ⚠️ Zastrzeżenie (Disclaimer)

Narzędzia służą wyłącznie do celów edukacyjnych i testów bezpieczeństwa (pentestingu) za zgodą właściciela aplikacji. Wykorzystywanie znalezionych kluczy bez uprawnień jest nielegalne i nieetyczne.
