// Register the `black` command globally (npm link) so users can run
// `black eclipse` from anywhere. Silent no-op if link already exists or fails.
const { execSync } = require("child_process");

try {
  execSync("black status", { stdio: "ignore", timeout: 10000 });
  console.log("[setup] 'black' command already registered globally.");
} catch {
  try {
    execSync("npm link", { stdio: "ignore", timeout: 60000 });
    console.log("[setup] 'black' command registered globally — run 'black eclipse' from anywhere.");
  } catch {
    console.warn("[setup] Could not register 'black' globally (npm link failed).");
    console.warn("         Run manually from this folder: npm link");
  }
}