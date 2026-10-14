"use client";

import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const TIERS = [
  {
    name: "Look things up",
    body: "I can read your own policies, check what's covered, and work out deadlines and documents — on my own, any time.",
  },
  {
    name: "Draft, but not send",
    body: "I can prepare a claim draft or a calculation, but it's just a draft until you see it.",
  },
  {
    name: "Submit, only after you confirm",
    body: "Actually sending a claim or booking a call-back happens only after you tap Confirm. I can't skip that step, even if you ask me to.",
  },
  {
    name: "Money and identity: never by me",
    body: "I can never move money, change a payout account, or edit who you are. Those requests go to the insurer through a verified, human channel — I'll open a ticket for you, nothing more.",
  },
];

export function SecurityInfoDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="How this works" className="h-8 w-8 sm:h-9 sm:w-9">
          <ShieldCheck className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>How ClauseGuard keeps you in control</DialogTitle>
          <DialogDescription>
            I can look up your policies and draft claims on my own. I only submit a claim or touch a sensitive
            request after you explicitly confirm. I can never move money or change your bank details.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {TIERS.map((t, i) => (
            <div key={t.name} className="flex gap-3 rounded-xl border border-border bg-muted/50 p-3">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                {i}
              </span>
              <div>
                <p className="text-sm font-medium">{t.name}</p>
                <p className="mt-0.5 text-sm text-muted-foreground">{t.body}</p>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Every answer is checked against the actual wording of your policy and names the clause behind it; every
          action is logged in a tamper-evident record. This is informative, not financial advice — your
          insurer&rsquo;s policy wording is what finally decides a claim.
        </p>
      </DialogContent>
    </Dialog>
  );
}
