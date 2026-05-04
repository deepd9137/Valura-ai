"""
System prompt builder for the intent classifier.

Kept separate from classifier.py so the prompt can be tuned
without touching the LLM-call path.
"""
from typing import List

_AGENT_DESCRIPTIONS = """
## Agent taxonomy — pick EXACTLY one:

| agent | route here when |
|---|---|
| portfolio_health | user asks about their OWN portfolio: health check, diversification, concentration, performance, benchmark comparison, holdings review |
| market_research | factual/recent info about a specific instrument, sector, index, FX rate, or market event — NOT about the user's own portfolio |
| investment_strategy | user asks whether they SHOULD buy/sell/hold/hedge/rebalance a specific asset, or asks for allocation strategy advice |
| financial_planning | long-term goal planning: retirement, FIRE, education fund, house down payment, savings rate — horizon-driven, not immediate trade |
| financial_calculator | deterministic numerical computation: DCA projections, compound interest, mortgage payments, future value, FX conversion, tax calculation |
| risk_assessment | risk metrics on the user's portfolio or a hypothetical: beta, max drawdown, VaR, stress tests, what-if scenarios, FX exposure |
| product_recommendation | recommend a specific fund, ETF, or product that fits the user's profile or stated criteria |
| predictive_analysis | forward-looking forecasts or trend extrapolation: "where will X be in N months/years?", "predict my portfolio value" |
| customer_support | platform issues, account questions, how to use the app, login problems, transaction history |
| general_query | educational definitions, greetings, thanks, conversational turns, gibberish, any query that doesn't fit above |
""".strip()

_ENTITY_VOCABULARY = """
## Entity extraction — include ONLY entities explicitly mentioned:

| field | type | notes |
|---|---|---|
| tickers | array[str] | uppercase, exchange-suffix where relevant: AAPL, ASML.AS, HSBA.L, 7203.T |
| amount | number | in the unit of currency field |
| currency | str | ISO 4217: USD, EUR, GBP, JPY |
| rate | number | decimal form: 0.08 for 8% |
| period_years | int | whole years only |
| frequency | str | one of: daily, weekly, monthly, yearly |
| horizon | str | one of: 6_months, 1_year, 5_years |
| time_period | str | one of: today, this_week, this_month, this_year |
| topics | array[str] | free-form concepts, lowercase |
| sectors | array[str] | industry sectors, lowercase |
| index | str | exact: S&P 500, FTSE 100, NIKKEI 225, MSCI World |
| action | str | one of: buy, sell, hold, hedge, rebalance |
| goal | str | one of: retirement, education, house, FIRE, emergency_fund |

Return only fields that are explicitly mentioned. Omit everything else.
""".strip()

_ROUTING_RULES = """
## Edge-case routing rules:

1. **Single ticker, no verb** (e.g. "AAPL", "asml.as") → market_research, entities: {tickers: [ticker]}
2. **Gibberish / unrecognisable input** (e.g. "abcdefg") → general_query, entities: {}
3. **Multi-intent** — pick the PRIMARY intent. "how is my portfolio doing and what should I sell?" → portfolio_health (portfolio is primary)
4. **Educational "what is X?"** about any financial concept → general_query (not market_research)
5. **"Should I buy/sell X?"** → investment_strategy (not market_research, not portfolio_health)
6. **Greetings, thanks, short social turns** → general_query
7. **Single-word company name without portfolio context** (e.g. "tell me about NVIDIA") → market_research
""".strip()


def build_system_prompt(prior_turns: List[str]) -> str:
    """
    Build the classifier system prompt.

    prior_turns: list of previous user messages in this session (oldest first).
    Injected so the classifier can resolve pronouns and dropped entities.
    """
    prior_section = ""
    if prior_turns:
        turns_text = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(prior_turns))
        prior_section = f"""
## Conversation context (prior user turns, oldest first):
{turns_text}

Use these to resolve ambiguous references in the current turn.
Example: if prior turn mentioned NVDA and current turn says "what about AMD?",
carry intent from prior turn and switch the ticker to AMD.
If the current turn introduces a completely new topic, do NOT carry prior entities.
""".strip()

    parts = [
        "You are the intent classifier for Valura, a wealth management platform.",
        "Your job: classify a user's financial query into exactly one agent and extract entities.",
        "Return ONLY valid JSON matching the schema — no prose, no markdown.",
        "",
        _AGENT_DESCRIPTIONS,
        "",
        _ENTITY_VOCABULARY,
        "",
        _ROUTING_RULES,
    ]

    if prior_section:
        parts += ["", prior_section]

    return "\n".join(parts)
