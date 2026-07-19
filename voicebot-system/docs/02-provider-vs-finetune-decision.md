# Provider vs. Fine-Tune/Self-Host — Decision Framework

Pricing snapshot gathered mid-July 2026 from vendor pricing pages. Vendor
pricing moves quarterly — re-verify before a contract. All are English-only
rates unless noted; Sarvam is India-focused but its English support and
pricing are included because it's commonly evaluated for India call-center
use cases.

## 1. The general rule

Default to a **third-party API** for all three stages at launch. Move a stage
to fine-tuning/self-hosting only when you can point to one of these, backed
by real production data:

- **Sustained volume** high enough that self-hosting is cheaper than API
  pricing at your utilization (see per-stage breakeven below) — this is
  almost always the deciding factor, not the others.
- **A narrow, high-value domain vocabulary** the general model keeps
  getting wrong (product names, medical/financial terms, regional accents)
  where a fine-tune measurably cuts error rate.
- **A hard data-residency or air-gap requirement** (regulated BFSI/healthcare
  data that legally cannot leave your infrastructure) that no API vendor's
  compliance posture satisfies.
- **Latency headroom you can't buy** — you've already picked the fastest
  API option and it's still not fast enough, so co-located self-hosting is
  the only lever left.

If none of those apply, a fine-tune/self-host effort is very likely to cost
more in engineering time and ongoing GPU/ops burden than it saves.

## 2. STT / ASR

| Provider | Price (streaming, English) | Notes |
|---|---|---|
| AssemblyAI (batch) | ~$0.0025/min | Cheapest, but batch only — not for live calls |
| Deepgram Nova-3 (pre-recorded) | ~$0.0043/min | |
| Deepgram Nova-3 (streaming) | ~$0.0077/min | Sub-300ms, proven at scale, $200 free credit |
| Sarvam Saaras (STT) | ~₹30/hour (~$0.006/min) | Strong on Indian-accented English and code-switching; India data hosting |
| Self-hosted Whisper (open weights) | GPU cost only, no per-minute fee | Needs GPU infra + ops; breakeven typically only above very high sustained concurrency |

**Decision:** Start with Deepgram (accuracy) or AssemblyAI (cost) for a
generic English accent target. **If your callers are predominantly Indian-English
speakers with regional accents/code-switching (Hinglish creeping in even on an
"English" line), Sarvam Saaras is worth a head-to-head accuracy test** —
Indian-accent word-error-rate is the one place a global provider can lag a
India-specific model. Move to self-hosted Whisper only once you're consistently
processing enough volume (very roughly, hundreds of thousands of minutes/month
sustained) that GPU cost + ops staffing undercuts API pricing — model this
explicitly in the cost calculator before committing.

## 3. LLM

| Provider (fast/conversational tier) | Price per 1M tokens (in/out) | Notes |
|---|---|---|
| GPT-4o-mini | $0.15 / $0.60 | Good default, fast, cheap |
| Claude Haiku 4.5 | $1 / $5 | Higher accuracy than mini-tier competitors on instruction-following; still fast |
| Gemini 2.5 Flash | ~$0.30 / $2.50 | Competitive, strong multimodal if ever needed |
| Sarvam-M (chat) | ~₹4 / ₹16 per 1M (~$0.05/$0.19) | Cheapest of the set; tuned for Indian context/names, weaker general reasoning than frontier mini-tier models |

**Decision:** Use a fast/cheap tier model (mini/Haiku/Flash class) for the
conversational turn — never a frontier reasoning model in the live call path,
the latency cost isn't worth it. Add a **complexity router**: send routine
turns (FAQ, transactional flows, confirmations) to the cheap model, and only
escalate genuinely ambiguous or high-stakes turns (e.g., a complaint, a
large-amount transaction) to a stronger model. This routing pattern alone
typically cuts LLM spend 60-80% versus sending every turn to one model.

**Fine-tuning the LLM** rarely beats a well-built system prompt + retrieval
(RAG) for a voicebot, because voicebot conversations are usually narrow,
templated, and tool-call-heavy — exactly what in-context instructions and
retrieval handle well without the cost/latency of a custom model. Consider
fine-tuning only if: (a) you have thousands of labeled real transcripts
showing a specific, repeated failure mode a bigger prompt can't fix, or
(b) you need the model to consistently follow a rigid output format/tool
schema at very low latency and prompting isn't reliable enough.

## 4. TTS

| Provider | Price per 1M characters | Notes |
|---|---|---|
| Google/AWS Polly Standard | $4 | Cheapest, robotic quality — fine for IVR menus, not for conversational bot |
| Azure Neural | $16 (commitment tiers as low as $7.50) | Good quality/cost balance, widest language/voice catalog |
| AWS Polly Neural | $16-19.20 | Comparable to Azure |
| Deepgram Aura-2 | $30 (₹ equivalent) | Built for real-time voice agents, sub-100ms |
| Sarvam Bulbul v3 | ₹15-30/10K chars (~$18-36/1M) | Best-in-class for Indian-accented English/Hinglish naturalness; sub-250ms streaming |
| ElevenLabs | $50-60+/1M (Flash/Turbo) | Best expressiveness/voice cloning, most expensive by far |

**Decision:** For a standard customer-support voicebot, **Azure Neural or
Deepgram Aura** give the best cost/quality/latency balance. Reach for
**ElevenLabs only if voice cloning or unusually expressive/emotional delivery
is a product requirement** — it's 3-4x the cost of the mid-tier options for a
quality gain that customer-support callers mostly won't notice over the phone.
If your bot's persona needs to sound distinctly Indian rather than a generic
US/UK English voice, **Sarvam Bulbul** is worth testing even for an
English-only line — it's tuned for Indian prosody and handles
name/number/currency pronunciation (₹, PIN codes, Indian phone number
cadence) more naturally than global providers.

**Custom/cloned voice** (a branded voice) is a one-time or low-recurring cost
with most vendors (Azure Custom Neural Voice, ElevenLabs Professional Voice
Cloning) rather than a "fine-tune" in the ML-training sense — worth it once
the bot has a fixed brand identity, not worth building in-house TTS from
scratch.

## 5. Weighted scoring template

Use this per stage when you have 2-3 finalist vendors. Weight columns to your
priorities (cost / latency / accuracy / data residency), score each vendor
1-5 per column, multiply, sum.

| Criterion | Weight | Vendor A | Vendor B | Vendor C |
|---|---|---|---|---|
| Cost at your projected volume | | | | |
| Latency (p50/p95, measured, not spec sheet) | | | | |
| Accuracy on your actual call recordings (not vendor benchmark) | | | | |
| Data residency / compliance fit | | | | |
| Integration effort / SDK maturity | | | | |
| **Weighted total** | | | | |

Always validate accuracy/latency claims against a sample of your own real
call audio before committing — vendor benchmark numbers are consistently
optimistic relative to real-world noisy phone audio, accented speech, and
code-switching.

## 6. Revisit cadence

Re-run this comparison every 2-3 months for the first year (LLM/TTS pricing
has dropped 60-80%+ over the past two years and continues to move quickly),
then quarterly once stable. Keep the per-call cost/latency logging described
in `01-tech-infrastructure.md` running continuously — it's the input this
framework needs to stay grounded in your actual traffic, not vendor marketing.
