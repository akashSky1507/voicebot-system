# voicebot-system

Reference architecture, cost model, and a build-vs-buy decision framework for a
production **English (India) voicebot** — the pipeline that turns a phone call
into ASR/STT → LLM → TTS → audio back to the caller.

Scope: outbound/inbound telephony voice bot, English only, India-hosted or
India-serving. The frameworks generalize to other languages, but the pricing
in `cost-calculator/` is built around English-first providers plus Sarvam AI
(the leading India-specific stack), since that's the common real-world choice
set for this use case.

## Why this repo exists

Every voicebot project asks the same four questions, once per pipeline stage:

1. **STT (speech→text):** which vendor, and is self-hosted Whisper/fine-tune worth it?
2. **LLM (the brain):** which model tier, and does fine-tuning beat a good system prompt?
3. **TTS (text→speech):** which voice vendor, and is a custom/cloned voice worth the cost?
4. **Infra:** what does it cost end-to-end at your call volume, and where does the money actually go?

This repo answers all four with a repeatable framework instead of a one-time
opinion, because provider pricing and model quality shift every quarter.

## Repo structure

```
voicebot-system/
├── README.md                              this file
├── docs/
│   ├── 01-tech-infrastructure.md          pipeline architecture, latency budget, infra stack
│   └── 02-provider-vs-finetune-decision.md  buy-vs-fine-tune framework for ASR/LLM/TTS
└── cost-calculator/
    └── index.html                         interactive $/₹ cost calculator (open in any browser)
```

## Pipeline at a glance

```
  Caller (PSTN/mobile)
        │
        ▼
  ┌─────────────┐    telephony/SIP trunk (Exotel, Ozonetel, Twilio, Plivo)
  │  Telephony  │
  └──────┬──────┘
         ▼
  ┌─────────────┐    streaming ASR/STT — turns audio into text as the caller speaks
  │  STT/ASR    │    (Deepgram / AssemblyAI / Sarvam Saaras / self-hosted Whisper)
  └──────┬──────┘
         ▼
  ┌─────────────┐    turn-taking + intent + response generation
  │  LLM/Orch.  │    (GPT-4o-mini / Claude Haiku / Gemini Flash / Sarvam-M,
  │  (+ RAG/    │     behind an orchestrator: Pipecat, LiveKit Agents, or custom)
  │   tools)    │
  └──────┬──────┘
         ▼
  ┌─────────────┐    streaming TTS — text back into natural speech
  │  TTS        │    (ElevenLabs / Azure Neural / Deepgram Aura / Sarvam Bulbul)
  └──────┬──────┘
         ▼
  Caller hears response  (target: <800ms first-audio latency, end to end)
```

See `docs/01-tech-infrastructure.md` for the full architecture, latency budget
per stage, and hosting/observability recommendations.

## The core decision, in one paragraph

For a first production voicebot, **default to third-party APIs for all three
stages** (STT, LLM, TTS) and only fine-tune or self-host a specific stage once
you have production call data proving that stage is the accuracy, cost, or
latency bottleneck. Fine-tuning/self-hosting wins mainly at high sustained
volume, with a narrow domain vocabulary, or under strict data-residency
requirements — not by default. The full scoring framework, with real
provider/pricing tables, is in `docs/02-provider-vs-finetune-decision.md`.

## Cost calculator

Open `cost-calculator/index.html` directly in a browser (no install needed).
It lets you set call volume, average call length, and pick providers per
stage, and shows monthly cost in USD and INR, broken down by pipeline stage.
Pricing is seeded with rates gathered mid-July 2026 — vendor pricing changes
often, so treat it as a modeling tool, not a live quote; re-check vendor
pricing pages before budgeting a contract.

## Next steps to turn this into a real repo

- `git init`, commit these files, push to your org's GitHub/GitLab.
- Add a `LICENSE` and `CONTRIBUTING.md` if this will be shared externally.
- Once you've picked providers, add an `infra/` folder with IaC (Terraform/Pulumi)
  for the orchestrator, telephony webhook endpoints, and logging/observability stack.
