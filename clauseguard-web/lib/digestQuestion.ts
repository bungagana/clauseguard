import type { DigestResponse } from "./types";

type DigestItem = DigestResponse["items"][number];

/** A short, natural question for a digest card click — never the long pre-composed digest sentence. */
export function digestItemQuestion(item: DigestItem): string {
  if (item.action?.prompt) return item.action.prompt;
  switch (item.kind) {
    case "POLICY_EXPIRES":
      return `Bagaimana cara memperpanjang ${item.product_name}?`;
    case "PREMIUM_DUE":
      return `Bagaimana cara membayar premi ${item.product_name} yang jatuh tempo?`;
    case "SPECIFIED_WAITING_ENDS":
      return `Apa yang berubah setelah masa tunggu ${item.product_name} berakhir?`;
    case "FILING_DEADLINE":
      return item.claim_id
        ? `Apa status klaim ${item.claim_id} dan dokumen apa yang masih kurang?`
        : `Apa tenggat pengajuan klaim untuk ${item.product_name}?`;
    case "CLAIM_STATUS":
      return item.claim_id
        ? `Apa status klaim ${item.claim_id} sekarang, dan apa yang perlu saya lakukan?`
        : `Bagaimana status klaim saya di ${item.product_name}?`;
    case "PREMIUM_OVERDUE":
      return `Premi ${item.product_name} menunggak. Bagaimana cara melunasinya dan apa akibatnya untuk pertanggungan saya?`;
    case "GRACE_ENDS":
      return `Masa tenggang ${item.product_name} hampir berakhir. Apa yang harus saya lakukan agar polis tidak lapse?`;
    case "SURVIVAL_PERIOD_ENDS":
      return `Kapan manfaat klaim ${item.product_name} bisa dibayarkan?`;
    default:
      return `Jelaskan soal ${item.product_name}.`;
  }
}
