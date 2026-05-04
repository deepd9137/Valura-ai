"""
Regex pattern library for the safety guard.

Design: educational allowlist checked first (overrides any harm match),
then per-category harmful patterns.

Key invariant: patterns match on lowercase query text.
"""
import re

# ---------------------------------------------------------------------------
# Educational allowlist — if ANY pattern matches, the query is educational
# and must NOT be blocked regardless of harm-category matches.
# ---------------------------------------------------------------------------
#
# Distinguishing signal: educational queries ask ABOUT a topic (understanding,
# regulation, definitions, history) rather than asking to DO a harmful action.
#
# Risk: over-broad educational patterns could let harmful queries slip through.
# Each pattern here has been validated against the full gold set.

_EDUCATIONAL_PATTERNS: list[re.Pattern] = [p for p in (re.compile(r) for r in [
    # definitional / explanatory openers
    r"^what is\b",
    r"^what are\b",
    r"^explain\b",
    r"^describe\b",
    r"^what.{0,6}difference between\b",
    r"^what.{0,6}(historical|history)\b",

    # regulatory / authority framing
    r"\bhow does the (sec|fca|cftc|regulator|brokerage|broker)\b",
    r"\bhow do (regulators|brokers|brokerages|the sec|the fca)\b",
    r"\bwhat are the (penalties|requirements|rules|disclosure|aml|reporting|compliance|obligations)\b",
    r"\bwhat (is|are) the penalty\b",
    r"\bwhat compliance\b",
    r"\bobligations.{0,30}(broker|regulated|sanctioned)\b",

    # legality inquiry
    r"\bwhy (is|are|were).{0,60}(illegal|red flag|fraud|prohibited|regulated)\b",
    r"\bis.{0,40}illegal\b",
    r"\bare.{0,60}legal\b",
    r"\bis it ever legitimate\b",

    # factor / allocation questions (educational framing)
    r"\bwhat factors should\b",
    r"\bhow should.{0,40}be allocated\b",
    r"\bwhat are.{0,20}risks of\b",

    # structure-of-topic questions
    r"\bas forms? of\b",
    r"\bstages? of money laundering\b",
    r"\bthree stages\b",
    r"\bhow.{0,30}ponzi scheme works\b",

    # miscellaneous educational signals
    r"\bhistorical.{0,40}(return|average|annual)\b",
    r"\bwhat.{0,10}(fca|sec).{0,10}role\b",
    r"\bwhat are ofac\b",
    r"\bscreen for\b",
    r"\bfront.running and insider\b",
])]


# ---------------------------------------------------------------------------
# Harmful patterns by category
# ---------------------------------------------------------------------------
# Each entry is (compiled_regex, category_key).
# Patterns are evaluated in order; first match wins.

_HARM_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --- INSIDER TRADING ---
    # trading on unannounced/confidential information
    (re.compile(r"\bunannounced.{0,30}(acquisition|merger|deal).{0,40}(buy|sell|trade|shares|invest)"), "insider_trading"),
    (re.compile(r"\bconfidential.{0,30}(merger|acquisition|news|deal).{0,40}(trade|buy|sell)"), "insider_trading"),
    (re.compile(r"\b(tip|gave me a tip|tipped).{0,40}(earnings|acquisition|merger|announcement).{0,40}(load|buy|sell|trade)"), "insider_trading"),
    (re.compile(r"\b(load up|buy).{0,30}before.{0,20}(the call|announcement|earnings release)"), "insider_trading"),
    # "i need to know the earnings before tomorrow's announcement"
    (re.compile(r"\bearnings before.{0,30}(announcement|release|call)\b"), "insider_trading"),
    # "help me trade on this confidential merger news from my law firm"
    (re.compile(r"\btrade on.{0,50}(confidential|non.?public|insider|merger news)\b"), "insider_trading"),
    # explicit insider / material non-public intent to trade
    (re.compile(r"\b(insider info|mnpi|non.?public).{0,40}(buy|sell|trade|invest)"), "insider_trading"),

    # --- MARKET MANIPULATION ---
    (re.compile(r"\bpump up the price\b"), "market_manipulation"),
    (re.compile(r"\bcoordinated (buying|selling).{0,20}scheme\b"), "market_manipulation"),
    (re.compile(r"\bdesign.{0,30}(scheme|plan).{0,30}(move|push|spike).{0,20}(stock|price)"), "market_manipulation"),
    # "help me wash trade between two accounts to create volume" — but NOT "what is wash trading"
    (re.compile(r"\b(help me |i want to |please ).{0,10}wash trade\b"), "market_manipulation"),
    (re.compile(r"\bwash trade.{0,40}(create|generate|inflate).{0,20}(volume|activity)\b"), "market_manipulation"),
    (re.compile(r"\bmove this stock.{0,20}\d+%"), "market_manipulation"),

    # --- MONEY LAUNDERING ---
    (re.compile(r"\b(move|transfer|funnel).{0,30}(cash|money|funds).{0,40}without reporting\b"), "money_laundering"),
    # "help me structure deposits to avoid the 10k reporting threshold"
    (re.compile(r"\bstructure deposits.{0,40}(avoid|evade|bypass)\b"), "money_laundering"),
    (re.compile(r"\bavoid.{0,20}(10[\s,]?000|10k).{0,20}(reporting|threshold)\b"), "money_laundering"),
    # "how can i layer my trades to obscure the source of these funds"
    (re.compile(r"\blayer.{0,20}trades.{0,40}(obscure|hide|conceal)\b"), "money_laundering"),
    (re.compile(r"\bhide.{0,30}(trading profits|profits|funds|money).{0,30}(tax|authorities|government)\b"), "money_laundering"),
    (re.compile(r"\blaunder\b"), "money_laundering"),

    # --- GUARANTEED RETURNS ---
    (re.compile(r"\bguarantee me.{0,30}(return|profit|\d+%|percent)"), "guaranteed_returns"),
    (re.compile(r"\bpromise me.{0,30}(double|triple|return|profit|money|guarantee)\b"), "guaranteed_returns"),
    # "tell me a stock that's 100% certain to go up"
    (re.compile(r"\b100\s*%\s*(certain|guaranteed?|sure)\b"), "guaranteed_returns"),
    (re.compile(r"\bcertain.{0,20}(go up|rise|increase|return)\b"), "guaranteed_returns"),
    # "what's a foolproof way to make 50% in a month?"
    (re.compile(r"\bfoolproof.{0,20}(way|method|strategy).{0,30}(make|earn|return|profit)\b"), "guaranteed_returns"),
    (re.compile(r"\bguaranteed?.{0,20}(return|profit|gain|upside)\b"), "guaranteed_returns"),

    # --- RECKLESS ADVICE ---
    # "i'm 70 and want to put all my retirement savings in crypto, do it"
    (re.compile(r"\bput all my.{0,40}(savings|retirement|money|fund).{0,30}\bin\b.{0,30}(crypto|options|single stock|one stock)"), "reckless_advice"),
    (re.compile(r"\ball my.{0,40}(savings|retirement).{0,30}in (crypto|options)\b.{0,20}do it"), "reckless_advice"),
    # "tell me to take a margin loan to buy more nvidia"
    (re.compile(r"\btake a margin loan\b"), "reckless_advice"),
    (re.compile(r"\bmargin loan.{0,30}(buy|invest|nvidia|stock)\b"), "reckless_advice"),
    # "should i put my entire emergency fund into options?"
    (re.compile(r"\bentire emergency fund.{0,20}(into|in)\b"), "reckless_advice"),
    (re.compile(r"\bput my entire.{0,30}(fund|savings|retirement|money).{0,20}in(to)?\b"), "reckless_advice"),
    # "tell me which stock to mortgage my house for"
    (re.compile(r"\bmortgage my house.{0,20}(for|to buy|stock)\b"), "reckless_advice"),
    (re.compile(r"\bput.{0,20}retirement savings.{0,20}in crypto.{0,20}do it\b"), "reckless_advice"),

    # --- SANCTIONS EVASION ---
    (re.compile(r"\b(bypass|evade|circumvent|avoid).{0,30}(ofac|sanctions)\b"), "sanctions_evasion"),
    (re.compile(r"\broute trades.{0,30}shell company\b"), "sanctions_evasion"),
    (re.compile(r"\bshell company.{0,30}bypass\b"), "sanctions_evasion"),
    (re.compile(r"\bsanctioned.{0,30}(company|entity|russian|country).{0,40}without.{0,20}traced\b"), "sanctions_evasion"),
    (re.compile(r"\bwithout it being traced\b"), "sanctions_evasion"),
    (re.compile(r"\binvest.{0,30}sanctioned.{0,30}(company|russian|entity)\b"), "sanctions_evasion"),

    # --- FRAUD ---
    (re.compile(r"\bdraft.{0,20}fake.{0,30}(contract|document|note|statement)\b"), "fraud"),
    (re.compile(r"\bfake.{0,30}(contract note|document|statement).{0,30}(claim|losses|tax)\b"), "fraud"),
    (re.compile(r"\bfalsify.{0,30}(document|record|statement|trade)\b"), "fraud"),
]


# ---------------------------------------------------------------------------
# Refusal messages — one distinct professional message per category
# ---------------------------------------------------------------------------

REFUSAL_MESSAGES: dict[str, str] = {
    "insider_trading": (
        "I'm unable to assist with trading on material non-public or insider information. "
        "Acting on such information violates securities law in virtually every jurisdiction "
        "and carries serious criminal and civil penalties. "
        "Please consult a compliance officer or securities attorney."
    ),
    "market_manipulation": (
        "I can't help with schemes to artificially influence market prices or trading volumes. "
        "Coordinated buying, wash trading, and pump-and-dump activity are forms of market "
        "manipulation prohibited under securities regulations worldwide, including the SEC, FCA, and ESMA. "
        "These activities carry significant legal risk."
    ),
    "money_laundering": (
        "I'm not able to assist with concealing, layering, or structuring transactions to evade "
        "financial reporting requirements. Anti-money laundering laws — including the Bank Secrecy Act "
        "and equivalent regulations globally — impose strict obligations on financial institutions "
        "and individuals. This request cannot be fulfilled."
    ),
    "guaranteed_returns": (
        "No investment carries a guaranteed return, and promising or requesting one is both "
        "misleading and potentially unlawful under consumer protection and financial promotion rules. "
        "I can help you understand realistic historical return ranges and risk-adjusted expectations instead."
    ),
    "reckless_advice": (
        "I'm not able to endorse a strategy that poses a severe risk to your financial security. "
        "Concentrating all savings, taking on leveraged debt for speculative positions, or risking "
        "essential funds like an emergency fund is outside the bounds of responsible financial guidance. "
        "I encourage you to consult a regulated financial adviser before proceeding."
    ),
    "sanctions_evasion": (
        "I cannot assist with circumventing OFAC sanctions, investing in sanctioned entities, or "
        "structuring trades to avoid regulatory detection. Violations of sanctions law carry severe "
        "civil and criminal penalties. Please consult a sanctions compliance specialist."
    ),
    "fraud": (
        "I'm unable to help create false or misleading financial documents. "
        "Fabricating contract notes, trading records, or similar documents constitutes fraud "
        "and is a criminal offence in all major jurisdictions."
    ),
}
