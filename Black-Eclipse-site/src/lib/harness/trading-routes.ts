// Pure broker-route allowlist, kept out of the Next.js route module so it can be
// tested without server-only imports. The proxy uses it for every method.

const ID = "[A-Za-z0-9_-]+";
const CONNECTION = new RegExp(`^connections/${ID}$`);
const CONNECTION_READ = new RegExp(`^connections/${ID}/(account|positions|orders|events|reconciliation|fills)$`);
const CONNECTION_QUOTE = new RegExp(`^connections/${ID}/quote$`);
const CONNECTION_SYMBOL = new RegExp(`^connections/${ID}/symbols/[A-Za-z0-9._#-]+$`);
const CONNECTION_TEST = new RegExp(`^connections/${ID}/test$`);
const CONNECTION_CONTROL = new RegExp(`^connections/${ID}/(arm|disarm|kill|sync)$`);
const CONNECTION_MANDATE = new RegExp(`^connections/${ID}/mandates$`);
const MANDATE_REVOKE = new RegExp(`^mandates/${ID}/revoke$`);
const ORDER_LEDGER = new RegExp(`^connections/${ID}/orders/ledger$`);
const ORDER_PREVIEW = new RegExp(`^connections/${ID}/orders/preview$`);
const ORDER_SUBMIT = new RegExp(`^connections/${ID}/orders/submit$`);
const ORDER_CANCEL = new RegExp(`^connections/${ID}/orders/\\d+/cancel$`);
const ORDER_MODIFY = new RegExp(`^connections/${ID}/orders/\\d+/modify$`);
const POSITION_CLOSE = new RegExp(`^connections/${ID}/positions/\\d+/close$`);
const POSITION_MODIFY = new RegExp(`^connections/${ID}/positions/\\d+/modify$`);
const POSITIONS_CLOSE = new RegExp(`^connections/${ID}/positions/close$`);
const ORDER_GET = new RegExp(`^orders/${ID}$`);
const APPROVAL_DECIDE = new RegExp(`^approvals/${ID}/decide$`);

export function isAllowedTradingRoute(method: string, path: string[]): boolean {
  const target = path.join("/");
  if (method === "GET") {
    return (
      target === "brokers" ||
      target === "connections" ||
      target === "approvals" ||
      target === "mandates" ||
      CONNECTION.test(target) ||
      CONNECTION_READ.test(target) ||
      CONNECTION_QUOTE.test(target) ||
      CONNECTION_SYMBOL.test(target) ||
      ORDER_LEDGER.test(target) ||
      ORDER_GET.test(target)
    );
  }
  if (method === "POST") {
    return (
      target === "connections" ||
      CONNECTION_TEST.test(target) ||
      CONNECTION_CONTROL.test(target) ||
      CONNECTION_MANDATE.test(target) ||
      MANDATE_REVOKE.test(target) ||
      ORDER_PREVIEW.test(target) ||
      ORDER_SUBMIT.test(target) ||
      ORDER_CANCEL.test(target) ||
      ORDER_MODIFY.test(target) ||
      POSITION_CLOSE.test(target) ||
      POSITION_MODIFY.test(target) ||
      POSITIONS_CLOSE.test(target) ||
      APPROVAL_DECIDE.test(target)
    );
  }
  if (method === "PATCH" || method === "DELETE") {
    return CONNECTION.test(target);
  }
  return false;
}
