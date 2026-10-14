import type { ClarificationRequest } from "./types";

// Phrases the fact binder recognises (regex first, model second) for each yes/no slot, in the
// language the conversation is being held in.
const PHRASES: Record<string, Record<"en" | "id", { yes: string; no: string }>> = {
  facility_bpjs_partner: {
    en: { yes: "Yes, it is a BPJS partner hospital.", no: "No, it is a non-BPJS private hospital." },
    id: { yes: "Ya, rumah sakitnya mitra BPJS.", no: "Tidak, rumah sakit swasta non-BPJS." },
  },
  facility_in_network: {
    en: { yes: "Yes, the hospital is in-network.", no: "No, the hospital is out of network." },
    id: { yes: "Ya, rumah sakitnya rekanan asuransi.", no: "Tidak, rumah sakitnya bukan rekanan." },
  },
  license_valid: {
    en: { yes: "Yes, my licence was valid at the time.", no: "No, my licence had expired." },
    id: { yes: "Ya, SIM saya masih berlaku saat itu.", no: "Tidak, SIM saya sudah kadaluarsa." },
  },
  is_accident: {
    en: { yes: "Yes, it was an accident.", no: "No, it was an illness, not an accident." },
    id: { yes: "Ya, karena kecelakaan.", no: "Bukan, karena sakit, bukan kecelakaan." },
  },
  is_emergency: {
    en: { yes: "Yes, it was an emergency admission.", no: "No, it was not an emergency." },
    id: { yes: "Ya, masuk lewat IGD, darurat.", no: "Tidak, bukan kondisi darurat." },
  },
  work_related: {
    en: { yes: "Yes, it happened while I was working.", no: "No, it was not work related." },
    id: { yes: "Ya, kejadiannya saat saya sedang bekerja.", no: "Tidak, bukan saat bekerja." },
  },
  rider_attached: {
    en: { yes: "Yes, the rider is attached to my policy.", no: "No, I do not have that rider." },
    id: { yes: "Ya, rider itu ada di polis saya.", no: "Tidak, saya tidak punya rider itu." },
  },
};

export interface QuickReply {
  label: string;
  text: string;
}

export function quickRepliesFor(clarification: ClarificationRequest, language: "en" | "id" = "en"): QuickReply[] {
  const slot = clarification.slot.toLowerCase();
  const values = Object.keys(clarification.verdict_by_value).map((v) => v.toLowerCase());
  const boolean = values.length === 0 || values.every((v) => v === "true" || v === "false");
  if (!boolean) return [];
  const p = PHRASES[slot]?.[language] ?? PHRASES[slot]?.en;
  if (!p) return [];
  return [
    { label: language === "id" ? "Ya" : "Yes", text: p.yes },
    { label: language === "id" ? "Tidak" : "No", text: p.no },
  ];
}
