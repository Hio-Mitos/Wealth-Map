"""
WealthMap – Live Market Data
Fetches current prices (and supporting metadata) for portfolio assets using
free, keyless APIs.

Stocks / ETFs / Bonds / Mutual Funds / Commodities / Crypto → yfinance
Crypto fallback → CoinGecko (no key required)
Real Estate / Other → manual valuation only (no live source)

All network calls are wrapped in try/except so a missing internet
connection (e.g. inside a sandboxed build) degrades gracefully instead
of crashing the app — `update_all_prices()` simply skips assets it
can't price and reports how many it updated.
"""

from typing import Optional, Dict, List
from datetime import datetime, timezone

from src.models.database import AssetType, PortfolioAsset


class MarketDataService:

    # Asset types that can have a live market price
    LIVE_TYPES = {
        AssetType.STOCK, AssetType.ETF, AssetType.BOND,
        AssetType.MUTUAL_FUND, AssetType.CRYPTO, AssetType.COMMODITY,
    }

    # Common crypto ticker -> CoinGecko id, used as a fallback if yfinance
    # doesn't return a price for a "XXX-USD" style ticker.
    COINGECKO_IDS: Dict[str, str] = {
        "BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether",
        "BNB": "binancecoin", "XRP": "ripple", "SOL": "solana",
        "ADA": "cardano", "DOGE": "dogecoin", "DOT": "polkadot",
        "MATIC": "matic-network", "LTC": "litecoin", "AVAX": "avalanche-2",
        "LINK": "chainlink", "TRX": "tron", "USDC": "usd-coin",
    }

    # Curated catalogue of well-known assets per type, used to populate a
    # searchable picker so the user can select a name and have its ticker
    # (and vice versa) filled in automatically. Not exhaustive — the user
    # can still type any custom ticker.
    KNOWN_ASSETS: Dict[AssetType, List[tuple]] = {
        AssetType.STOCK: [
            ("Apple Inc.", "AAPL"), ("Microsoft Corporation", "MSFT"),
            ("Alphabet Inc. (Google) Class A", "GOOGL"), ("Amazon.com Inc.", "AMZN"),
            ("Tesla Inc.", "TSLA"), ("Meta Platforms Inc.", "META"),
            ("NVIDIA Corporation", "NVDA"), ("Berkshire Hathaway Class B", "BRK-B"),
            ("JPMorgan Chase & Co.", "JPM"), ("Visa Inc.", "V"),
            ("Johnson & Johnson", "JNJ"), ("Walmart Inc.", "WMT"),
            ("Procter & Gamble Co.", "PG"), ("The Walt Disney Company", "DIS"),
            ("Netflix Inc.", "NFLX"), ("Coca-Cola Company", "KO"),
            ("Pfizer Inc.", "PFE"), ("Intel Corporation", "INTC"),
            ("Advanced Micro Devices", "AMD"), ("Boeing Company", "BA"),
            ("Exxon Mobil Corporation", "XOM"), ("Chevron Corporation", "CVX"),
            ("McDonald's Corporation", "MCD"), ("Nike Inc.", "NKE"),
            ("Starbucks Corporation", "SBUX"), ("PayPal Holdings", "PYPL"),
            ("Adobe Inc.", "ADBE"), ("Salesforce Inc.", "CRM"),
            ("Costco Wholesale Corporation", "COST"), ("Home Depot Inc.", "HD"),
        ],
        AssetType.ETF: [
            ("Vanguard S&P 500 ETF", "VOO"), ("SPDR S&P 500 ETF Trust", "SPY"),
            ("Invesco QQQ Trust (Nasdaq-100)", "QQQ"), ("Vanguard Total Stock Market ETF", "VTI"),
            ("iShares Core S&P 500 ETF", "IVV"), ("Vanguard Developed Markets ETF", "VEA"),
            ("Vanguard Emerging Markets ETF", "VWO"), ("Vanguard Total Bond Market ETF", "BND"),
            ("iShares Core US Aggregate Bond ETF", "AGG"), ("SPDR Gold Shares", "GLD"),
            ("iShares Russell 2000 ETF", "IWM"), ("SPDR Dow Jones Industrial Average ETF", "DIA"),
            ("Technology Select Sector SPDR Fund", "XLK"), ("Financial Select Sector SPDR Fund", "XLF"),
            ("ARK Innovation ETF", "ARKK"), ("Vanguard Information Technology ETF", "VGT"),
        ],
        AssetType.MUTUAL_FUND: [
            ("Vanguard 500 Index Fund (Admiral)", "VFIAX"), ("Fidelity 500 Index Fund", "FXAIX"),
            ("Vanguard Total Stock Market Index (Admiral)", "VTSAX"),
            ("Schwab S&P 500 Index Fund", "SWPPX"), ("Fidelity ZERO Total Market Index Fund", "FZROX"),
            ("Vanguard Total International Stock Index (Admiral)", "VTIAX"),
            ("Vanguard Total Bond Market Index (Admiral)", "VBTLX"),
            ("American Funds Growth Fund of America", "AGTHX"),
        ],
        AssetType.CRYPTO: [
            ("Bitcoin", "BTC-USD"), ("Ethereum", "ETH-USD"), ("BNB", "BNB-USD"),
            ("Solana", "SOL-USD"), ("XRP", "XRP-USD"), ("Cardano", "ADA-USD"),
            ("Dogecoin", "DOGE-USD"), ("Polkadot", "DOT-USD"), ("Polygon", "MATIC-USD"),
            ("Litecoin", "LTC-USD"), ("Avalanche", "AVAX-USD"), ("Chainlink", "LINK-USD"),
            ("TRON", "TRX-USD"), ("Tether USD", "USDT-USD"), ("USD Coin", "USDC-USD"),
        ],
        AssetType.COMMODITY: [
            ("Gold", "GC=F"), ("Silver", "SI=F"), ("Crude Oil (WTI)", "CL=F"),
            ("Natural Gas", "NG=F"), ("Copper", "HG=F"), ("Platinum", "PL=F"),
            ("Corn", "ZC=F"), ("Wheat", "ZW=F"), ("Soybeans", "ZS=F"), ("Coffee", "KC=F"),
        ],
    }

    def supports_live(self, asset_type: AssetType) -> bool:
        return asset_type in self.LIVE_TYPES

    def known_assets(self, asset_type: AssetType) -> List[tuple]:
        """Return [(name, ticker), ...] of well-known assets for this type."""
        return self.KNOWN_ASSETS.get(asset_type, [])

    def suggested_ticker_format(self, asset_type: AssetType) -> str:
        hints = {
            AssetType.STOCK:       "e.g. AAPL, MSFT, TSLA",
            AssetType.ETF:         "e.g. VOO, SPY, QQQ",
            AssetType.BOND:        "e.g. BND, TLT (bond ETF ticker)",
            AssetType.MUTUAL_FUND: "e.g. VFIAX, FXAIX",
            AssetType.CRYPTO:      "e.g. BTC-USD, ETH-USD",
            AssetType.COMMODITY:   "e.g. GC=F (gold), SI=F (silver), CL=F (oil)",
            AssetType.REAL_ESTATE: "Manual valuation only — update price by hand",
            AssetType.OTHER:       "Manual valuation only — update price by hand",
        }
        return hints.get(asset_type, "")

    # ── Single asset ────────────────────────────────────────────────────────

    def fetch_price(self, ticker: str, asset_type: AssetType) -> Optional[float]:
        """Backwards-compatible: just the price."""
        quote = self.fetch_quote(ticker, asset_type)
        return quote.get("price") if quote else None

    def fetch_quote(self, ticker: str, asset_type: AssetType) -> Optional[Dict]:
        """Backwards-compatible: returns just the quote dict, or None."""
        quote, _reason = self.fetch_quote_with_reason(ticker, asset_type)
        return quote

    def fetch_quote_with_reason(self, ticker: str, asset_type: AssetType) -> "tuple[Optional[Dict], Optional[str]]":
        """
        Return (quote, reason). `quote` is a dict with the current price plus
        whatever metadata is available (currency, previous_close,
        day_change_abs, day_change_pct, market_cap, week52_high,
        week52_low), or None on failure. `reason` is a short human-readable
        explanation of the *last* failure, useful for diagnostics — None if
        a quote was found.

        Tries multiple sources, in order, so a missing optional package
        (yfinance) or one API being unreachable doesn't block the others:
          1. yfinance (if installed) — richest metadata
          2. Yahoo Finance chart endpoint via plain HTTP — works for stocks,
             ETFs, mutual funds, commodities, and most crypto pairs, with no
             extra dependency beyond `requests`
          3. CoinGecko (crypto only) — final fallback
        """
        if not ticker or not self.supports_live(asset_type):
            return None, "this asset type doesn't support live prices"
        ticker = ticker.strip().upper()

        # Crypto tickers are commonly entered without the "-USD" suffix
        # (e.g. "BTC" instead of "BTC-USD") — normalize so all three
        # sources below have the best chance of recognising it.
        candidates = [ticker]
        if asset_type == AssetType.CRYPTO and "-" not in ticker:
            candidates = [f"{ticker}-USD", ticker]

        last_reason = "ticker not recognized by any price source"
        for cand in candidates:
            quote = self._fetch_yfinance_quote(cand)
            if quote:
                return quote, None
            quote, reason = self._fetch_yahoo_chart_quote(cand)
            if quote:
                return quote, None
            if reason:
                last_reason = reason

        if asset_type == AssetType.CRYPTO:
            for cand in candidates:
                quote, reason = self._fetch_coingecko_quote(cand)
                if quote:
                    return quote, None
                if reason:
                    last_reason = reason

        return None, last_reason

    def _fetch_yfinance_quote(self, ticker: str) -> Optional[Dict]:
        """Richest source, but optional — returns None silently if yfinance
        isn't installed or errors, so callers fall through to other sources."""
        try:
            import yfinance as yf
        except ImportError:
            return None
        try:
            t = yf.Ticker(ticker)
            fi = t.fast_info

            def g(*names):
                for name in names:
                    try:
                        if hasattr(fi, "get"):
                            v = fi.get(name)
                        else:
                            v = getattr(fi, name, None)
                    except Exception:
                        v = None
                    if v is not None:
                        return v
                return None

            price = g("lastPrice", "last_price")
            prev_close = g("previousClose", "previous_close", "regularMarketPreviousClose")

            if price is None or prev_close is None:
                hist = t.history(period="5d")
                closes = hist["Close"].dropna() if not hist.empty else None
                if price is None and closes is not None and len(closes):
                    price = float(closes.iloc[-1])
                if prev_close is None and closes is not None and len(closes) > 1:
                    prev_close = float(closes.iloc[-2])

            if price is None:
                return None

            price = float(price)
            day_change_abs = day_change_pct = None
            if prev_close:
                prev_close = float(prev_close)
                day_change_abs = price - prev_close
                day_change_pct = (day_change_abs / prev_close * 100) if prev_close else None

            return {
                "price": price,
                "currency": g("currency") or "",
                "previous_close": prev_close,
                "day_change_abs": day_change_abs,
                "day_change_pct": day_change_pct,
                "market_cap": g("marketCap", "market_cap"),
                "week52_high": g("yearHigh", "year_high"),
                "week52_low": g("yearLow", "year_low"),
            }
        except Exception as e:
            print(f"[MarketData] yfinance failed for {ticker}: {e}")
            return None

    def _fetch_yahoo_chart_quote(self, ticker: str) -> "tuple[Optional[Dict], Optional[str]]":
        """
        Fetch price + previous close directly from Yahoo Finance's public
        chart endpoint via plain HTTP. No extra package required (only
        `requests`, already a core dependency), so this works even when
        yfinance isn't installed or is broken by an API change.
        """
        try:
            import requests
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                params={"interval": "1d", "range": "5d"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            if resp.status_code == 404:
                return None, f"ticker '{ticker}' not found"
            resp.raise_for_status()
            data = resp.json()
            result = (data.get("chart") or {}).get("result")
            if not result:
                err = (data.get("chart") or {}).get("error")
                if err:
                    return None, str(err.get("description", err))
                return None, f"no data returned for '{ticker}'"

            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            prev_close = meta.get("previousClose") or meta.get("chartPreviousClose")

            if price is None:
                # Fall back to the last close in the price series
                quotes = (result[0].get("indicators", {}).get("quote") or [{}])[0]
                closes = [c for c in (quotes.get("close") or []) if c is not None]
                if closes:
                    price = closes[-1]
                    if prev_close is None and len(closes) > 1:
                        prev_close = closes[-2]

            if price is None:
                return None, f"no price data for '{ticker}'"

            price = float(price)
            day_change_abs = day_change_pct = None
            if prev_close:
                prev_close = float(prev_close)
                day_change_abs = price - prev_close
                day_change_pct = (day_change_abs / prev_close * 100) if prev_close else None

            return {
                "price": price,
                "currency": meta.get("currency") or "",
                "previous_close": prev_close,
                "day_change_abs": day_change_abs,
                "day_change_pct": day_change_pct,
                "market_cap": None,
                "week52_high": meta.get("fiftyTwoWeekHigh"),
                "week52_low": meta.get("fiftyTwoWeekLow"),
            }, None
        except requests.exceptions.RequestException as e:
            return None, f"network error reaching Yahoo Finance ({e.__class__.__name__})"
        except Exception as e:
            return None, f"unexpected error: {e}"

    def _fetch_coingecko_quote(self, ticker: str) -> "tuple[Optional[Dict], Optional[str]]":
        try:
            import requests
            base_ticker = ticker.replace("-USD", "").replace("USD", "").strip()
            coin_id = self.COINGECKO_IDS.get(base_ticker, base_ticker.lower())
            resp = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd",
                       "include_24hr_change": "true", "include_market_cap": "true"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8
            )
            resp.raise_for_status()
            data = resp.json().get(coin_id, {})
            price = data.get("usd")
            if price is None:
                return None, f"'{ticker}' not recognized by CoinGecko"
            return {
                "price": float(price),
                "currency": "USD",
                "previous_close": None,
                "day_change_abs": None,
                "day_change_pct": data.get("usd_24h_change"),
                "market_cap": data.get("usd_market_cap"),
                "week52_high": None,
                "week52_low": None,
            }, None
        except requests.exceptions.RequestException as e:
            return None, f"network error reaching CoinGecko ({e.__class__.__name__})"
        except Exception as e:
            return None, f"unexpected error: {e}"

    # ── Bulk refresh ────────────────────────────────────────────────────────

    def update_all_prices(self, portfolio_service, assets: Optional[List[PortfolioAsset]] = None) -> Dict:
        """
        Refresh price + metadata for every asset that has a ticker and a
        live-data-capable asset type, recording a historical snapshot for
        each successful update. Returns a summary dict:
        {"updated": int, "skipped": int, "failed": [(ticker, reason), ...]}
        """
        if assets is None:
            assets = portfolio_service.db.query(PortfolioAsset).filter_by(is_active=True).all()

        updated, skipped, failed = 0, 0, []
        for asset in assets:
            if not self.supports_live(asset.asset_type) or not asset.ticker:
                skipped += 1
                continue
            quote, reason = self.fetch_quote_with_reason(asset.ticker, asset.asset_type)
            if quote is None or quote.get("price") is None:
                failed.append((asset.ticker, reason or "unknown error"))
                continue
            portfolio_service.record_price_snapshot(asset, quote, source="market")
            updated += 1
        return {"updated": updated, "skipped": skipped, "failed": failed}
