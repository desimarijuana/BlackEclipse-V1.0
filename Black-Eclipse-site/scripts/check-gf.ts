import axios from "axios";

async function main() {
  try {
    const res = await axios.get("https://www.google.com/finance/quote/AAPL:NYSE", {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
      },
      timeout: 10000,
    });
    console.log("Status:", res.status);
    console.log("Length:", res.data.length);
    console.log("Has data-last-price:", res.data.includes("data-last-price"));
    console.log("Has NlB0jf (old price class):", res.data.includes("YMlKec"));
    // Print a snippet around any price-like content
    const idx = res.data.indexOf("AAPL");
    console.log("Snippet around AAPL:", res.data.slice(idx, idx + 500));
  } catch (e: any) {
    console.log("Error:", e?.message);
    if (e?.response) console.log("Status:", e.response.status);
  }
}
main();
