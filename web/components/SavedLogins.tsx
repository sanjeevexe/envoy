"use client";

// Saved logins (api/autofill.py): at an app's sign-in screen, the phone's own password manager fills in a login you saved
// there, and Envoy asks you before it presses Sign in. Envoy never sees or types the password. Off unless you turn it
// on, separately for the emulators and for your own phone.
import { useEffect, useState } from "react";
import { Card, Section } from "@/components/ui";
import { api, post } from "@/lib/api";

type Kinds = { emulator: boolean; phone: boolean };
const KINDS: { key: keyof Kinds; label: string; detail: string }[] = [
  { key: "emulator", label: "On the emulators", detail: "Envoy\u2019s emulators, with the Google account signed in there" },
  { key: "phone", label: "On your Android phone", detail: "With the password manager you use on it" },
];

export default function SavedLogins() {
  const [on, setOn] = useState<Kinds | null>(null);
  useEffect(() => { api<{ autofill: Kinds }>("/api/settings/signin").then((r) => setOn(r.autofill)).catch(() => {}); }, []);
  if (!on) return null;
  const set = (key: keyof Kinds, value: boolean) => {
    setOn({ ...on, [key]: value });
    post<{ autofill: Kinds }>("/api/settings/signin", { autofill: { ...on, [key]: value } }).then((r) => setOn(r.autofill)).catch(() => {});
  };
  return (
    <Section title="Use saved logins from your phone's password manager" intro={<>When an app asks you to sign in, Envoy can tap a login you saved in the phone&rsquo;s password manager. The manager fills it in, and Envoy asks you before it presses Sign in. Envoy never sees or types your password. If anything doesn&rsquo;t match, it hands the phone to you as before.</>}>
      <Card className="overflow-hidden">
        {KINDS.map((k) => (
          <label key={k.key} className="flex min-h-[60px] items-center justify-between gap-3 border-b border-divider px-4 py-2 last:border-b-0">
            <span className="min-w-0">
              <span className="block text-row font-semibold">{k.label}</span>
              <span className="block text-meta-2 text-muted">{k.detail}</span>
            </span>
            <input type="checkbox" aria-label={`Saved logins ${k.label.toLowerCase()}`} checked={on[k.key]} onChange={(e) => set(k.key, e.target.checked)} />
          </label>
        ))}
      </Card>
    </Section>
  );
}
