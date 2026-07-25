import yfinance as yf
import requests_cache
from datetime import timedelta

def get_stock_prices(tickers, cache_minutes=5):
    # 1. Önbellekli bir oturum (session) oluştur.
    # Bu işlem, bulunduğun klasöre 'yfinance_cache.sqlite' adında bir dosya açar.
    session = requests_cache.CachedSession(
        'yfinance_cache',
        expire_after=timedelta(minutes=cache_minutes)
    )

    # 2. Hisseleri boşlukla ayrılmış bir string'e çevir (Örn: "THYAO.IS AAPL")
    ticker_string = " ".join(tickers)

    # 3. Veriyi tek seferde topluca indir.
    # period="2d" diyerek hem dünkü kapanışı hem bugünü alıyoruz.
    # session parametresi ile yfinance'e "benim cache mekanizmamı kullan" diyoruz.
    print("Veriler kontrol ediliyor... (Önbellekte varsa anında gelir)")
    data = yf.download(ticker_string, period="2d", session=session, progress=False)

    results = {}

    # 4. Gelen veriyi işle ve hesaplamalar için hazırla
    for ticker in tickers:
        try:
            # Çoklu hisse çektiğimizde yfinance sütunları gruplar.
            if len(tickers) > 1:
                close_prices = data['Close'][ticker]
            else:
                close_prices = data['Close']

            # Boş (NaN) verileri temizle
            close_prices = close_prices.dropna()

            if len(close_prices) >= 2:
                prev_close = close_prices.iloc[-2] # Dünün kapanışı
                current_price = close_prices.iloc[-1] # Anlık fiyat (Bugün)
            else:
                prev_close = close_prices.iloc[0]
                current_price = close_prices.iloc[0]

            results[ticker] = {
                "anlik_fiyat": float(current_price),
                "dunku_kapanis": float(prev_close),
                "gunluk_degisim_tl": float(current_price - prev_close)
            }
        except Exception as e:
            print(f"{ticker} işlenirken hata oluştu: {e}")
            
    return results

# --- Kodu Test Etmek İçin ---
if __name__ == "__main__":
    # BİST hisseleri sonuna .IS almalıdır.
    portfoyum = ["THYAO.IS", "TUPRS.IS", "AAPL"]
    
    fiyatlar = get_stock_prices(portfoyum, cache_minutes=5)
    
    for hisse, veri in fiyatlar.items():
        print(f"{hisse} -> Anlık: {veri['anlik_fiyat']:.2f} | Dünkü Kapanış: {veri['dunku_kapanis']:.2f}")