# Tech Infrastructure

## 1. Pipeline architecture

A voice bot call is a real-time loop across four stages. The two things that
make it hard (vs. a text chatbot) are **streaming** (you cannot wait for a
full sentence before responding) and **latency budget** (humans notice a gap
over ~800ms-1s as "the bot froze").

```
Caller ─▶ Telephony/SIP ─▶ VAD ─▶ Denoiser ─▶ STT (streaming) ─▶ Orchestrator/LLM ─▶ TTS (streaming) ─▶ Caller
                            │         │              │                    │                  │
                       end-of-turn  noise/echo   partial +           tool calls,        first-audio-
                       detection    cleanup      final transcripts  RAG lookups,        byte streamed
                                                                     turn-taking          back as it's
                                                                                          generated
```

See `architecture/pipeline.md` for a rendered (Mermaid) version of this same
flow, plus a stage-by-stage table of what each box does.

**Telephony layer (India-specific options):** Exotel, Ozonetel, Knowlarity,
Airtel IQ (India-native, handle DLT/TRAI compliance, cheaper local minutes),
vs. Twilio/Plivo (global, better docs/SDKs, pricier local termination).
For a domestic India voicebot, an India-native telephony provider is usually
the right default purely on per-minute call cost and regulatory familiarity
(DLT registration, TRAI call-recording rules).

**Orchestration layer:** this is the glue code that manages the STT→LLM→TTS
loop, barge-in/interruption handling, and turn-taking. STT, LLM, and TTS are
independent microservices, each its own vendor endpoint — the orchestrator
holds a persistent **WebSocket** connection open to each one and streams
audio/text in, partial results back out. That means each turn pays three
separate network round trips (orchestrator↔STT, orchestrator↔LLM,
orchestrator↔TTS) on top of every vendor's own processing time — see
`architecture/pipeline.md` for the full topology diagram and per-hop latency
guide. Orchestrator options:
- **Pipecat** (open source, Python) — widely used, good STT/LLM/TTS provider adapters.
- **LiveKit Agents** (open source + hosted option) — strong for WebRTC-based
  voice, also has a hosted "LiveKit Cloud" tier.
- **Vendor-bundled** (Deepgram Voice Agent API, Retell AI, Vapi, Bland AI) —
  faster to ship, less control, and you're paying a markup on top of the
  underlying STT/LLM/TTS costs (often 30-100%+). Reasonable for a pilot;
  usually gets swapped for a custom orchestrator once volume justifies it.

**Compute/hosting:** the orchestrator itself is lightweight (mostly I/O-bound,
proxying audio/text between APIs), so it typically runs fine on small
containers (e.g., 2 vCPU / 4GB) behind an autoscaling group — AWS ECS/Fargate,
GCP Cloud Run, or a K8s deployment. The exception is if you self-host STT/LLM/TTS
models, which need GPU instances (see `02-provider-vs-finetune-decision.md`).

## 2. Latency budget

Target end-to-end (caller stops speaking → bot's first audio byte): **under ~800ms**
for the interaction to feel natural; under ~1.5s is tolerable; beyond that,
callers start talking over the bot or hanging up.

| Stage | Typical latency (streaming, good providers) | Notes |
|---|---|---|
| Network/telephony hop | 50-150ms | SIP trunk + jitter buffer |
| VAD (end-of-turn detection) | 5-40ms | In-process in the orchestrator — no separate network hop; WebRTC VAD (fastest, rule-based) to pyannote (most accurate, heaviest) |
| Denoiser | 0-20ms | In-process in the orchestrator — no separate network hop; skip for already-clean audio, add for noisy call-center environments |
| WebSocket hop overhead (orchestrator ↔ STT/LLM/TTS) | ~5-15ms same-region, ~20-60ms+ cross-region, ×3 (one per service) | STT, LLM, and TTS are independent microservices reached over a persistent WebSocket — see `architecture/pipeline.md`. This is pure network RTT on top of each vendor's own processing time below |
| STT (partial→final) | 100-300ms | Streaming ASR, not batch — vendor's own processing time, excludes the WebSocket hop above |
| LLM time-to-first-token | 150-500ms (fast tier) | Use a fast/cheap tier (GPT-5.1, GPT-4o-mini, Haiku, Flash, Sarvam-M, or GPT-5.4's nano tier) — GPT-5.4's full reasoning mode alone can add seconds and should never sit in the live call path |
| TTS time-to-first-audio-byte | 75-250ms | Flash/streaming-optimized TTS models only — non-streaming TTS can add 1-2s |
| **Total** | **~500ms-1.5s** | |

Practical levers, roughly in order of impact:
1. Use a small/fast LLM for the conversational turn (GPT-5.1, GPT-4o-mini,
   Haiku, Flash, or Sarvam-M class), not a frontier reasoning model — GPT-5.4's
   default reasoning behavior alone can add seconds; if you want that model
   family in the live path, use its nano tier or force low/no reasoning effort.
2. Use streaming APIs at every stage (streaming STT, streaming LLM tokens,
   streaming TTS) — never batch any of the three in a live call.
3. Co-locate: run the orchestrator in the same cloud region as your STT/LLM/TTS
   providers' nearest edge, and as close to your telephony provider's POP as
   possible. For India traffic, prefer providers with a Mumbai/Singapore region.
4. Pre-fetch/cache anything that doesn't depend on the caller's exact words
   (static prompts, common lookups).

## 3. Infra stack recommendation (mid-scale India voicebot)

| Layer | Recommendation | Why |
|---|---|---|
| Telephony | Exotel or Ozonetel (India-native) | DLT compliance built in, cheaper domestic minutes, local support |
| Orchestrator | Pipecat or LiveKit Agents, self-hosted on Fargate/Cloud Run | Avoids per-minute markup of bundled voice-agent platforms once volume is real |
| STT | Deepgram or Sarvam Saaras (see decision doc) | Streaming, sub-300ms, proven at scale |
| LLM | GPT-5.1 / GPT-4o-mini / Claude Haiku / Gemini Flash class model behind a router (GPT-5.4 only via its nano tier, or with low/no reasoning effort) | Fast enough for real-time turn-taking; escalate only complex turns to a bigger model |
| TTS | Deepgram Aura, Azure Neural, or Sarvam Bulbul | Streaming, sub-250ms first-byte |
| Observability | Call recordings + transcript logs to S3/GCS, dashboards in Grafana/Datadog, per-call cost tagging from day one | You cannot make provider decisions later without per-call cost/latency/accuracy data |
| Data residency | Confirm each vendor's data-processing region; India's DPDP Act and RBI/IRDAI rules (for BFSI) may require in-India data handling | Check before signing any vendor contract, not after |

## 4. Observability — instrument this from day one

Whatever providers you pick, log per call: STT latency + confidence score,
LLM latency + token counts, TTS latency + character count, and call outcome
(completed / dropped / escalated to human). This is the data set that lets
you revisit the provider-vs-fine-tune decision with real numbers in 2-3 months
instead of guessing. Cost attribution per call, per stage, is what actually
drives the fine-tune/self-host decision — see `02-provider-vs-finetune-decision.md`.
