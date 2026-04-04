import httpx
from datetime import datetime, timedelta


DEFILLAMA_BASE_URL = "https://api.llama.fi"


async def get_tvl_growth(protocol_name: str) -> dict:
    url = f"{DEFILLAMA_BASE_URL}/protocol/{protocol_name.lower()}"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)

            if response.status_code == 404:
                return {"error": f"Protokol '{protocol_name}' tidak ditemukan di DefiLlama."}

            if response.status_code != 200:
                return {"error": f"DefiLlama API error: {response.status_code}"}

            data = response.json()

            tvl_data = data.get("tvl", [])

            if not tvl_data:
                return {"error": f"Data TVL untuk '{protocol_name}' tidak tersedia."}

            # Ambil TVL sekarang (index terakhir)
            current = tvl_data[-1]
            current_tvl = current["totalLiquidityUSD"]
            current_date = datetime.fromtimestamp(current["date"]).strftime("%d %b %Y")

            # Cari TVL 30 hari lalu
            target_date = datetime.now() - timedelta(days=30)
            past_entry = None

            for entry in reversed(tvl_data):
                entry_date = datetime.fromtimestamp(entry["date"])
                if entry_date <= target_date:
                    past_entry = entry
                    break

            if not past_entry:
                return {"error": f"Data 30 hari lalu untuk '{protocol_name}' tidak tersedia."}

            past_tvl = past_entry["totalLiquidityUSD"]
            past_date = datetime.fromtimestamp(past_entry["date"]).strftime("%d %b %Y")

            # Hitung growth
            if past_tvl == 0:
                return {"error": "TVL 30 hari lalu adalah 0, tidak bisa hitung growth."}

            growth = ((current_tvl - past_tvl) / past_tvl) * 100

            return {
                "protocol": data.get("name", protocol_name),
                "current_tvl": current_tvl,
                "current_date": current_date,
                "past_tvl": past_tvl,
                "past_date": past_date,
                "growth_percent": round(growth, 2)
            }

    except httpx.TimeoutException:
        return {"error": "DefiLlama API timeout. Coba lagi."}

    except Exception as e:
        return {"error": f"Error: {str(e)}"}


def format_tvl_result(result: dict) -> str:
    if "error" in result:
        return result["error"]

    growth = result["growth_percent"]
    arrow = "🟢 +" if growth >= 0 else "🔴 "

    current = result["current_tvl"]
    past = result["past_tvl"]

    def format_usd(value):
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        else:
            return f"${value:,.0f}"

    return (
        f"TVL {result['protocol']}:\n"
        f"- Sekarang ({result['current_date']}): {format_usd(current)}\n"
        f"- 30 hari lalu ({result['past_date']}): {format_usd(past)}\n"
        f"- Growth: {arrow}{growth}%"
    )
