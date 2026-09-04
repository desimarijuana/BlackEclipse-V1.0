import { guessSentiment } from "../src/lib/sentiment";

const cases: Array<[string, string]> = [
  ["Nvidia surges 8% on record earnings", "bullish"],
  ["Stocks rally as Fed signals rate cuts", "bullish"],
  ["Rates didn't fall as investors hoped", "bearish"], // negation flips "fall"
  ["Company fails to beat earnings estimates", "bearish"], // negation flips "beat"
  ["Market crashes as recession fears grow", "bearish"],
  ["Apple shares slip 0.3% in quiet trading", "neutral"], // weak single word
  ["Oil prices steady amid mixed signals", "neutral"],
  ["Tesla plunges after downgrade to sell", "bearish"],
  ["Economy adds jobs, unemployment not rising", "neutral"], // +1 -1(negated rise→+1? no: negated rise = -1) = 0 → neutral
  ["Economy adds jobs strongly as recovery accelerates", "bullish"],
  ["Stocks rally strongly on earnings beats", "bullish"],
  ["Profits collapse amid fraud probe", "bearish"],
];

let pass = 0;
for (const [text, expected] of cases) {
  const got = guessSentiment(text);
  const ok = got === expected;
  if (ok) pass++;
  console.log(`${ok ? "PASS" : "FAIL"} [${got}] ${text}`);
}
console.log(`${pass}/${cases.length} passed`);
if (pass < cases.length) process.exit(1);