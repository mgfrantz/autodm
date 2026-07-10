"""
Downtime Activities engine — DnD 5e between-adventures resolution rules.

The three DnD pillars (Combat, Exploration, Social) all have resolution engines
now, but the large chunk of an adventurer's life that happens *between* jobs —
**downtime** — had none. This module implements the PHB ch.8 "Downtime
Activities" and Xanathar's Guide to Everything ch.2 "Downtime Revisited" rules
as pure, fully-deterministic resolution functions.

Activities modelled (faithful to the source books):

* **Carousing** (XGE) — spend gold by social tier for a workweek of revelry;
  a d6 complication roll (1) triggers a tier-appropriate d20 complication,
  often resisted by a DC 10 save.
* **Crime** (XGE) — case a joint (casing check vs a quality DC) then run the
  heist (three skill checks); payout scales with casing + heist successes,
  capped at 0 if casing fails.
* **Gambling** (XGE) — wager gold across a series of d20 checks (DC 20);
  net winnings/losses scale with the win margin; d6 complication.
* **Pit Fighting** (XGE) — three physical checks vs DC; payouts of 0/50/150/500
  gp for 0–3 successes; d6 complication (injuries).
* **Research** (XGE) — pay per workweek, make checks (Arcana / Investigation /
  the relevant lore skill) vs a lore DC; successes reveal facts, failures
  produce false leads.
* **Relaxation** (PHB) — 1 gp/day; a week's rest removes minor ailments — here
  that means recovering **one** exhaustion level and clearing non-magical
  transient conditions, per the XGE "relaxing downtime" guidance.
* **Crafting** (PHB/XGE) — mundane crafting at 5 gp/day of progress; half the
  item's market value in raw materials; returns completion when progress meets
  the item's value.
* **Practicing a Profession** (XGE) — requires a relevant tool proficiency;
  grants a comfortable lifestyle plus an optional 1d25 gp per workweek.
* **Work** (PHB) — unskilled labour for a modest lifestyle (≈ 5 gp/week).
* **Training** (XGE) — learn a new language or tool proficiency; 250 days +
  250 gp (1 gp/day); returns day-progress and completes by granting the
  proficiency.
* **Religion** (XGE) — contemplative devotion; checks (Religion/Insight) vs
  DC for a moment of clarity (here: a one-level exhaustion ease on success).

The engine is **pure** — no database, no LLM. All dice are injectable (explicit
``roll`` ints, ``d6``/``d20`` ints, or a ``roller`` callable) for full
determinism in tests. Every resolver returns a :class:`DowntimeResult` carrying
the gold delta, days spent, a one-line narration, an optional complication, and
a structured ``details`` dict for the caller (API) to apply side effects.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# --------------------------------------------------------------------------- #
# Core constants (XGE measures downtime in the 5-day workweek)
# --------------------------------------------------------------------------- #

#: One XGE "workweek" is five 8-hour workdays.
WORKWEEK_DAYS: int = 5

#: Mundane crafting progress per workday of effort (PHB: 5 gp/day).
CRAFT_PROGRESS_PER_DAY: int = 5

#: Lifestyle costs in gold pieces per day (PHB ch.5 "Lifestyle Expenses").
LIFESTYLE_COST_PER_DAY: dict[str, float] = {
    "wretched": 0.0,
    "squalid": 0.1,
    "poor": 0.2,
    "modest": 1.0,
    "comfortable": 2.0,
    "wealthy": 4.0,
    "aristocratic": 10.0,
    "noble": 10.0,  # alias
}


# --------------------------------------------------------------------------- #
# Activity definitions + registry
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DowntimeActivityDef:
    """A downtime activity's fixed metadata (not its resolution)."""

    id: str
    name: str
    source: str           # "PHB" | "XGE"
    description: str
    category: str         # social | intrigue | wealth | crafting | study | rest | profession
    min_days: int = 1
    gold_per_day: int = 0
    requires_tool: Optional[str] = None
    requires_profession_tool: bool = False


DOWNTIME_ACTIVITIES: dict[str, DowntimeActivityDef] = {
    a.id: a for a in (
        DowntimeActivityDef(
            id="carousing", name="Carousing", source="XGE",
            category="social",
            description=(
                "Spend a workweek in revelry among a chosen social tier. "
                "Cost rises with the tier; a complication (d6=1) may follow."
            ),
        ),
        DowntimeActivityDef(
            id="crime", name="Crime", source="XGE",
            category="intrigue",
            description=(
                "Case a joint, then pull off a heist. Payout scales with the "
                "number of successful checks; complications abound."
            ),
        ),
        DowntimeActivityDef(
            id="gambling", name="Gambling", source="XGE",
            category="wealth",
            description=(
                "Wager gold on games of chance resolved by ability checks "
                "(DC 20). Win or lose by the margin of your successes."
            ),
        ),
        DowntimeActivityDef(
            id="pit_fighting", name="Pit Fighting", source="XGE",
            category="wealth",
            description=(
                "Brawl for coin. Three physical checks decide a purse of "
                "0/50/150/500 gp; injuries are a real risk."
            ),
        ),
        DowntimeActivityDef(
            id="research", name="Research", source="XGE",
            category="study",
            description=(
                "Pay to pore over tomes and lore. Checks reveal facts on "
                "success; failures breed false leads."
            ),
        ),
        DowntimeActivityDef(
            id="relaxation", name="Relaxation", source="PHB",
            category="rest",
            description=(
                "Live cheaply and rest. A week's relaxation removes minor "
                "ailments — easing one exhaustion level."
            ),
            gold_per_day=1,
        ),
        DowntimeActivityDef(
            id="crafting", name="Crafting", source="PHB",
            category="crafting",
            description=(
                "Craft a mundane item: half its value in materials, then 5 gp "
                "of progress per workday."
            ),
        ),
        DowntimeActivityDef(
            id="profession", name="Practicing a Profession", source="XGE",
            category="profession",
            requires_profession_tool=True,
            description=(
                "Practise a trade using a tool proficiency: a comfortable "
                "lifestyle plus 1d25 gp of extra earnings per workweek."
            ),
        ),
        DowntimeActivityDef(
            id="work", name="Work", source="PHB",
            category="profession",
            description=(
                "Unskilled labour for a modest lifestyle — roughly 5 gp a "
                "week, no tool proficiency required."
            ),
        ),
        DowntimeActivityDef(
            id="training", name="Training", source="XGE",
            category="study",
            description=(
                "Study under a tutor to learn a new language or tool "
                "proficiency: 250 days at 1 gp/day. Grants the proficiency "
                "on completion."
            ),
            gold_per_day=1,
            min_days=1,
        ),
        DowntimeActivityDef(
            id="religion", name="Religion", source="XGE",
            category="rest",
            description=(
                "Contemplative devotion. Checks (Religion/Insight) may grant a "
                "moment of clarity that eases exhaustion."
            ),
        ),
    )
}


def list_activities() -> list[DowntimeActivityDef]:
    """All available downtime activities, sorted by category then name."""
    return sorted(
        DOWNTIME_ACTIVITIES.values(),
        key=lambda a: (a.category, a.name),
    )


def get_activity(activity_id: str) -> Optional[DowntimeActivityDef]:
    """Look up a single activity by id (case-insensitive)."""
    if not activity_id:
        return None
    return DOWNTIME_ACTIVITIES.get(activity_id.strip().lower())


# --------------------------------------------------------------------------- #
# Result dataclass
# --------------------------------------------------------------------------- #

@dataclass
class DowntimeResult:
    """The outcome of resolving one downtime period.

    ``gold_delta`` is signed (negative = spent, positive = earned) and excludes
    lifestyle costs the caller may already account for. ``details`` carries
    structured, activity-specific data (e.g. checks rolled, progress made,
    complications to apply) that the API layer turns into character/world
    mutations.
    """

    activity: str
    days: int
    gold_delta: int = 0
    narration: str = ""
    complication: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def earned(self) -> int:
        return self.gold_delta if self.gold_delta > 0 else 0

    @property
    def spent(self) -> int:
        return -self.gold_delta if self.gold_delta < 0 else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity": self.activity,
            "days": self.days,
            "gold_delta": self.gold_delta,
            "narration": self.narration,
            "complication": self.complication,
            "details": self.details,
        }


# --------------------------------------------------------------------------- #
# Complication tables (compact but faithful to XGE)
# --------------------------------------------------------------------------- #
# Each table is a tuple of complication strings; a d20 is rolled and mapped
# (mod len) so the table is always in range. A complication may carry a DC and
# a save ability in its leading tag, e.g. "[DC10 Dex] ...". The resolver splits
# that tag out into DowntimeResult.details.

CAROUSING_COMPLICATIONS: dict[str, tuple[str, ...]] = {
    "lower": (
        "[DC10 Con] You drank something foul and spent the night heaving — you start the next day with 1 level of exhaustion.",
        "[DC10 Dex] A brawl broke out and you took a beating — lose 1d6 HP.",
        "You made a new friend in the gutter; you may meet them again.",
        "[DC10 Cha] You insulted a local cutpurse and now a small-time thief has it in for you.",
        "You won a silly bet and pocket a few extra coppers (+1d6 gp).",
        "[DC10 Dex] You were pickpocketed — lose 1d6 gp.",
    ),
    "middle": (
        "[DC10 Con] The wine was watered with something regrettable — start the next day with 1 level of exhaustion.",
        "[DC10 Wis] A charming new acquaintance turned out to be a confidence trickster — lose 2d6 gp.",
        "You networked well; a guild contact now looks on you favorably.",
        "[DC10 Dex] A duel of honor was narrowly avoided; you paid to smooth things over (−1d6×5 gp).",
        "You gambled on a local game and came out ahead (+2d6 gp).",
        "[DC10 Cha] You embarrassed yourself before an influential merchant.",
    ),
    "upper": (
        "[DC10 Con] The rare spirits disagreed with you — start the next day with 1 level of exhaustion.",
        "[DC10 Dex] A high-society rival arranged an 'accident' — lose 3d6 HP.",
        "[DC10 Wis] A noble's invitation was a trap; you were robbed of finery (−1d6×25 gp).",
        "You gained the ear of a minor noble; reputation with the local power rises.",
        "[DC10 Cha] A scandalous rumor about you begins to circulate.",
        "You won big at a private gaming table (+1d6×25 gp).",
    ),
}

CRIME_COMPLICATIONS: tuple[str, ...] = (
    "[DC10 Dex] A guard spotted you; you barely escaped but the heat is on.",
    "[DC10 Con] The job ran long and you slept in the cold — 1 exhaustion level.",
    "[DC10 Cha] An accomplice talked; you owe a favor to the local thieves' guild.",
    "The mark was already being watched by rivals; expect competition.",
    "[DC10 Wis] You were recognized despite the disguise; a witness can place you.",
    "A fence shorted you on the take — lose 1d6×10 gp.",
)

GAMBLING_COMPLICATIONS: tuple[str, ...] = (
    "[DC10 Cha] A sore loser accused you of cheating.",
    "[DC10 Dex] The house sent thugs to collect an imagined debt; lose 1d6 HP.",
    "[DC10 Wis] You bet on credit and now owe a dangerous figure money (−2d6 gp of debt).",
    "[DC10 Con] You drank through the whole game; start the next day with 1 exhaustion level.",
    "A fellow gambler took a shine to you — a new contact.",
    "[DC10 Int] A hustler ran a mark on you; lose 1d6 gp.",
)

PIT_FIGHTING_COMPLICATIONS: tuple[str, ...] = (
    "[DC10 Con] You took a brutal hit — lose 2d6 HP and gain 1 exhaustion level.",
    "[DC10 Str] A larger opponent flattened you; lose 3d6 HP.",
    "[DC10 Dex] You were thrown from the pit; lose 1d6 HP and gain 1 exhaustion level.",
    "[DC10 Con] An old injury flared — start the next day with 1 exhaustion level.",
    "You caught a promoter's eye; future purses may improve (reputation up).",
    "[DC10 Cha] You made an enemy of a rival fighter.",
)


def _pick_complication(
    table: tuple[str, ...],
    d20: Optional[int] = None,
) -> str:
    """Map a d20 onto a complication table (wraps with modulo)."""
    roll = d20 if (d20 is not None and 1 <= d20 <= 20) else random.randint(1, 20)
    return table[(roll - 1) % len(table)]


def _parse_complication_save(text: str) -> tuple[str, int, str]:
    """Extract a leading ``[DCn Ability]`` save tag from a complication.

    Returns ``(clean_text, dc, ability)``. ``ability`` is ``""`` when no save
    tag is present (the complication just happens, narrative-only).
    """
    text = text.strip()
    if not text.startswith("["):
        return text, 0, ""
    end = text.find("]")
    if end == -1:
        return text, 0, ""
    tag = text[1:end].strip()
    body = text[end + 1:].strip()
    # Expected form: "DC10 Con" / "DC 10 Dex" / "DC15 Wisdom"
    dc = 0
    ability = ""
    parts = tag.replace("DC", "").replace("dc", "").strip().split()
    for p in parts:
        if p.isdigit():
            dc = int(p)
        else:
            ability = p.lower()
    return body, dc, ability


def _complication_triggered(d6: Optional[int] = None) -> bool:
    """XGE: a complication arises on a d6 roll of 1."""
    roll = d6 if (d6 is not None and 1 <= d6 <= 6) else random.randint(1, 6)
    return roll == 1


# --------------------------------------------------------------------------- #
# Roll-helpers (all accept explicit values for determinism)
# --------------------------------------------------------------------------- #

Roller = Callable[[int], int]  # callable(sides) -> int in 1..sides


def _d(sides: int, value: Optional[int], roller: Optional[Roller]) -> int:
    if value is not None:
        return value
    if roller is not None:
        return roller(sides)
    return random.randint(1, sides)


def _check(
    modifier: int,
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    roll: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> tuple[int, int, bool]:
    """A single d20 ability check.

    Returns ``(roll_shown, total, success)``. Natural 1 is an automatic failure
    and natural 20 an automatic success (the d20 combat convention).
    """
    if advantage and disadvantage:
        advantage = disadvantage = False
    if roll is not None:
        first = roll
        second = roll
    else:
        first = _d(20, None, roller)
        second = _d(20, None, roller)
    if advantage:
        shown = max(first, second)
    elif disadvantage:
        shown = min(first, second)
    else:
        shown = first
    total = shown + modifier
    success = (shown == 20) or (shown != 1 and total >= dc)
    return shown, total, success


# --------------------------------------------------------------------------- #
# Per-activity resolvers
# --------------------------------------------------------------------------- #

#: Carousing cost per workweek, by social tier (XGE).
CAROUSING_COST_PER_WEEK: dict[str, int] = {
    "lower": 10,
    "middle": 50,
    "upper": 250,
}

#: Pit-fighting payouts by number of successes (0..3).
PIT_FIGHTING_PAYOUTS: tuple[int, ...] = (0, 50, 150, 500)


def carouse(
    tier: str = "middle",
    workweeks: int = 1,
    *,
    save_modifier: int = 0,
    d6: Optional[int] = None,
    complication_d20: Optional[int] = None,
    save_roll: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a period of Carousing (XGE).

    ``tier`` is ``"lower"``/``"middle"``/``"upper"``. ``workweeks`` multiplies
    the cost; a complication can arise each workweek. ``save_modifier`` is the
    ability modifier for any complication save (caller picks the relevant one).
    """
    tier = (tier or "middle").strip().lower()
    if tier not in CAROUSING_COST_PER_WEEK:
        tier = "middle"
    workweeks = max(1, int(workweeks))
    cost = CAROUSING_COST_PER_WEEK[tier] * workweeks
    days = WORKWEEK_DAYS * workweeks

    complication_text: Optional[str] = None
    save_used: Optional[int] = None
    save_succeeded: bool = True
    # Roll a complication per workweek; keep the first that triggers.
    for _ in range(workweeks):
        if not _complication_triggered(d6):
            continue
        table = CAROUSING_COMPLICATIONS[tier]
        raw = _pick_complication(table, complication_d20)
        body, dc, ability = _parse_complication_save(raw)
        if dc > 0 and ability:
            shown, total, save_succeeded = _check(
                save_modifier, dc, roll=save_roll, roller=roller,
            )
            save_used = shown
            complication_text = (
                f"{body} (DC {dc} {ability.capitalize()} save: "
                f"rolled {shown} → {'passed' if save_succeeded else 'failed'})."
            )
        else:
            complication_text = body
        break

    gold_delta = -cost
    if complication_text and not save_succeeded and tier in ("middle", "upper"):
        # A failed upper-society save can also dent the purse; we keep the
        # core cost as the gold delta and let the complication narrate the rest.
        pass

    narration = (
        f"Caroused ({tier} tier) for {workweeks} workweek(s) "
        f"({cost} gp, {days} days)."
    )
    return DowntimeResult(
        activity="carousing",
        days=days,
        gold_delta=gold_delta,
        narration=narration,
        complication=complication_text,
        details={
            "tier": tier,
            "workweeks": workweeks,
            "cost": cost,
            "save_roll": save_used,
            "save_succeeded": save_succeeded,
        },
    )


def crime(
    *,
    casing_modifier: int = 0,
    casing_dc: int = 15,
    heist_modifier: int = 0,
    heist_dc: int = 15,
    heist_checks: int = 3,
    max_payout: int = 1000,
    casing_roll: Optional[int] = None,
    heist_rolls: Optional[list[int]] = None,
    d6: Optional[int] = None,
    complication_d20: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a Crime job (XGE): casing the joint, then the heist.

    The heist only pays out if casing succeeds. Each successful heist check
    steps up the payout toward ``max_payout``. Casing + heist each take one
    workweek.
    """
    casing_dc = max(1, int(casing_dc))
    heist_dc = max(1, int(heist_dc))
    heist_checks = max(1, int(heist_checks))

    _, _, casing_ok = _check(casing_modifier, casing_dc, roll=casing_roll, roller=roller)

    successes = 0
    rolled: list[int] = []
    for i in range(heist_checks):
        r = heist_rolls[i] if (heist_rolls and i < len(heist_rolls)) else None
        shown, _, ok = _check(heist_modifier, heist_dc, roll=r, roller=roller)
        rolled.append(shown)
        if ok:
            successes += 1

    payout = 0
    if casing_ok:
        # Payout rises with successes; 0 successes still means nothing.
        if successes > 0:
            payout = min(max_payout, int(max_payout * successes / heist_checks))

    days = WORKWEEK_DAYS * 2  # casing + heist
    cost = 100  # XGE: casing the joint costs 100 gp
    gold_delta = payout - cost

    complication_text: Optional[str] = None
    if _complication_triggered(d6):
        body, dc, ability = _parse_complication_save(
            _pick_complication(CRIME_COMPLICATIONS, complication_d20)
        )
        complication_text = (
            f"{body}" if not (dc and ability) else
            f"{body} (DC {dc} {ability.capitalize()} save applies if you act on it)."
        )

    narration = (
        f"Cased a joint (DC {casing_dc}: {'success' if casing_ok else 'failure'}) "
        f"and ran a heist ({successes}/{heist_checks} checks at DC {heist_dc}): "
        f"{'netted ' + str(payout) + ' gp' if casing_ok and payout else 'no take'}."
    )
    return DowntimeResult(
        activity="crime",
        days=days,
        gold_delta=gold_delta,
        narration=narration,
        complication=complication_text,
        details={
            "casing_success": casing_ok,
            "casing_dc": casing_dc,
            "heist_successes": successes,
            "heist_checks": heist_checks,
            "heist_dc": heist_dc,
            "heist_rolls": rolled,
            "payout": payout,
            "cost": cost,
        },
    )


def gamble(
    wager: int = 100,
    *,
    modifier: int = 0,
    dc: int = 20,
    games: int = 3,
    rolls: Optional[list[int]] = None,
    d6: Optional[int] = None,
    complication_d20: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a Gambling session (XGE).

    The net gold is ``wager * (wins - losses) / games``: come out ahead by the
    win margin, lose by the loss margin, or break even. Wager is clamped to a
    minimum of 0. A d6=1 complication may follow.
    """
    wager = max(0, int(wager))
    dc = max(1, int(dc))
    games = max(1, int(games))

    wins = 0
    rolled: list[int] = []
    for i in range(games):
        r = rolls[i] if (rolls and i < len(rolls)) else None
        shown, _, ok = _check(modifier, dc, roll=r, roller=roller)
        rolled.append(shown)
        if ok:
            wins += 1
    losses = games - wins

    # Net fraction: (wins - losses) / games. e.g. 3-0 → +wager; 0-3 → −wager.
    net = int(wager * (wins - losses) / games)
    days = WORKWEEK_DAYS

    complication_text: Optional[str] = None
    if _complication_triggered(d6):
        body, dc_s, ability = _parse_complication_save(
            _pick_complication(GAMBLING_COMPLICATIONS, complication_d20)
        )
        complication_text = (
            f"{body}" if not (dc_s and ability) else
            f"{body} (DC {dc_s} {ability.capitalize()} save applies if you act on it)."
        )

    if net > 0:
        line = f"won {net} gp"
    elif net < 0:
        line = f"lost {abs(net)} gp"
    else:
        line = "broke even"
    narration = (
        f"Gambled a {wager} gp wager over {games} games (DC {dc}): "
        f"{line} ({wins} wins, {losses} losses)."
    )
    return DowntimeResult(
        activity="gambling",
        days=days,
        gold_delta=net,
        narration=narration,
        complication=complication_text,
        details={
            "wager": wager,
            "dc": dc,
            "games": games,
            "wins": wins,
            "losses": losses,
            "rolls": rolled,
            "net": net,
        },
    )


def pit_fight(
    *,
    modifier: int = 0,
    dc: int = 15,
    rolls: Optional[list[int]] = None,
    d6: Optional[int] = None,
    complication_d20: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a workweek of Pit Fighting (XGE): three checks → a purse."""
    dc = max(1, int(dc))
    successes = 0
    rolled: list[int] = []
    for i in range(3):
        r = rolls[i] if (rolls and i < len(rolls)) else None
        shown, _, ok = _check(modifier, dc, roll=r, roller=roller)
        rolled.append(shown)
        if ok:
            successes += 1
    payout = PIT_FIGHTING_PAYOUTS[min(successes, len(PIT_FIGHTING_PAYOUTS) - 1)]
    days = WORKWEEK_DAYS

    complication_text: Optional[str] = None
    if _complication_triggered(d6):
        body, dc_s, ability = _parse_complication_save(
            _pick_complication(PIT_FIGHTING_COMPLICATIONS, complication_d20)
        )
        complication_text = (
            f"{body}" if not (dc_s and ability) else
            f"{body} (DC {dc_s} {ability.capitalize()} save applies if you act on it)."
        )

    narration = (
        f"Fought in the pit ({successes}/3 checks at DC {dc}): "
        f"won a {payout} gp purse."
    )
    return DowntimeResult(
        activity="pit_fighting",
        days=days,
        gold_delta=payout,
        narration=narration,
        complication=complication_text,
        details={
            "dc": dc,
            "successes": successes,
            "payout": payout,
            "rolls": rolled,
        },
    )


def research(
    *,
    modifier: int = 0,
    dc: int = 15,
    workweeks: int = 1,
    cost_per_week: int = 25,
    roll: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a period of Research (XGE).

    One check per workweek (Arcana / Investigation / the relevant lore skill).
    Each success reveals a fact; each failure is a false lead that costs extra.
    """
    dc = max(1, int(dc))
    workweeks = max(1, int(workweeks))
    cost = cost_per_week * workweeks
    days = WORKWEEK_DAYS * workweeks

    facts = 0
    false_leads = 0
    rolled: list[int] = []
    for _ in range(workweeks):
        shown, _, ok = _check(modifier, dc, roll=roll, roller=roller)
        rolled.append(shown)
        if ok:
            facts += 1
        else:
            false_leads += 1

    # False leads add extra cost (bribe, time, retraction).
    extra = false_leads * 10
    gold_delta = -(cost + extra)

    narration = (
        f"Researched for {workweeks} workweek(s) (DC {dc}): uncovered "
        f"{facts} fact(s) with {false_leads} false lead(s), costing "
        f"{cost + extra} gp."
    )
    return DowntimeResult(
        activity="research",
        days=days,
        gold_delta=gold_delta,
        narration=narration,
        details={
            "dc": dc,
            "workweeks": workweeks,
            "facts": facts,
            "false_leads": false_leads,
            "cost": cost + extra,
            "rolls": rolled,
        },
    )


def relax(
    days: int = WORKWEEK_DAYS,
    *,
    current_exhaustion: int = 0,
    conditions: Optional[list[str]] = None,
) -> DowntimeResult:
    """Resolve a period of Relaxation (PHB).

    1 gp/day. A week (5 days) or more of rest removes minor ailments: here that
    means easing **one** exhaustion level and clearing a short list of
    non-magical transient conditions. Returns the resulting exhaustion and the
    conditions that should remain (caller applies them).
    """
    days = max(1, int(days))
    cost = days * 1  # 1 gp/day
    conditions = list(conditions or [])

    ease_exhaustion = 0
    if days >= WORKWEEK_DAYS and current_exhaustion > 0:
        ease_exhaustion = 1
    new_exhaustion = max(0, current_exhaustion - ease_exhaustion)

    # Non-magical, transient conditions relaxation can clear.
    clearable = {
        "frightened", "poisoned", "diseased",
        "exhaustion",  # handled via level, but listed for completeness
    }
    cleared: list[str] = []
    remaining: list[str] = []
    if days >= WORKWEEK_DAYS:
        for c in conditions:
            cl = str(c).strip().lower()
            if cl in clearable and cl != "exhaustion":
                cleared.append(cl)
            elif cl:
                remaining.append(cl)
    else:
        remaining = conditions

    narration = (
        f"Relaxed for {days} day(s) ({cost} gp). "
        + (
            f"Eased 1 exhaustion level (now {new_exhaustion}); "
            f"minor ailments cleared: {', '.join(cleared) or 'none'}."
            if days >= WORKWEEK_DAYS
            else "A day's rest, but true recovery needs a full week."
        )
    )
    return DowntimeResult(
        activity="relaxation",
        days=days,
        gold_delta=-cost,
        narration=narration,
        details={
            "exhaustion_before": current_exhaustion,
            "exhaustion_after": new_exhaustion,
            "exhaustion_delta": -ease_exhaustion,
            "cleared_conditions": cleared,
            "remaining_conditions": remaining,
            "cost": cost,
        },
    )


def craft(
    item_value: int,
    *,
    days: int = 1,
    progress_before: int = 0,
    proficiency_required: bool = True,
    has_proficiency: bool = True,
) -> DowntimeResult:
    """Resolve mundane Crafting (PHB/XGE).

    Progress accrues at 5 gp/day; materials cost half the item's value up front.
    ``progress_before`` lets a multi-week craft job accumulate. Returns
    completion when cumulative progress meets ``item_value``.
    """
    item_value = max(0, int(item_value))
    days = max(0, int(days))
    materials = (item_value + 1) // 2  # half, rounded up

    if proficiency_required and not has_proficiency:
        return DowntimeResult(
            activity="crafting",
            days=0,
            gold_delta=0,
            narration=(
                "Cannot craft without the relevant tool proficiency."
            ),
            details={
                "item_value": item_value,
                "complete": False,
                "reason": "no_proficiency",
            },
        )

    gained = days * CRAFT_PROGRESS_PER_DAY
    total = progress_before + gained
    complete = total >= item_value and item_value > 0
    progress_now = min(total, item_value) if complete else total

    # Gold delta: materials paid up front (only when first starting), and the
    # item is produced (worth item_value) on completion.
    starting = progress_before <= 0
    gold_delta = 0
    if starting:
        gold_delta -= materials
    if complete:
        gold_delta += item_value  # produced item's value

    if complete:
        line = f"Completed the item (worth {item_value} gp)."
    else:
        line = (
            f"Made {gained} gp of progress ({progress_now}/{item_value} gp)."
        )
    narration = (
        f"Crafted for {days} day(s): {line}"
    )
    return DowntimeResult(
        activity="crafting",
        days=days,
        gold_delta=gold_delta,
        narration=narration,
        details={
            "item_value": item_value,
            "materials": materials if starting else 0,
            "progress_before": progress_before,
            "progress_gained": gained,
            "progress_now": progress_now,
            "complete": complete,
            "starting": starting,
        },
    )


def practice_profession(
    *,
    workweeks: int = 1,
    tool_proficiency: bool = True,
    d25: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve Practicing a Profession (XGE).

    Requires a relevant tool proficiency. Grants a comfortable lifestyle; if the
    caller asks for extra coin, the worker earns 1d25 gp per workweek (the XGE
    roll). Without proficiency, the activity devolves to plain Work.
    """
    workweeks = max(1, int(workweeks))
    days = WORKWEEK_DAYS * workweeks

    if not tool_proficiency:
        # Falls back to unskilled labour (modest lifestyle, ~5 gp/week).
        earnings = 5 * workweeks
        narration = (
            f"Worked without a profession tool for {workweeks} workweek(s): "
            f"earned {earnings} gp at a modest lifestyle."
        )
        return DowntimeResult(
            activity="profession",
            days=days,
            gold_delta=earnings,
            narration=narration,
            details={
                "tool_proficiency": False,
                "workweeks": workweeks,
                "earnings": earnings,
                "lifestyle": "modest",
            },
        )

    earnings = 0
    rolls: list[int] = []
    for _ in range(workweeks):
        r = d25 if (d25 is not None) else _d(25, None, roller)
        rolls.append(r)
        earnings += r
    # Comfortable lifestyle offsets living costs (already net-positive here).
    narration = (
        f"Practiced a profession for {workweeks} workweek(s): earned "
        f"{earnings} gp at a comfortable lifestyle (rolls: {rolls})."
    )
    return DowntimeResult(
        activity="profession",
        days=days,
        gold_delta=earnings,
        narration=narration,
        details={
            "tool_proficiency": True,
            "workweeks": workweeks,
            "earnings": earnings,
            "rolls": rolls,
            "lifestyle": "comfortable",
        },
    )


def work(
    *,
    workweeks: int = 1,
) -> DowntimeResult:
    """Resolve unskilled Work (PHB): a modest lifestyle, ~5 gp/week."""
    workweeks = max(1, int(workweeks))
    days = WORKWEEK_DAYS * workweeks
    earnings = 5 * workweeks
    narration = (
        f"Laboured for {workweeks} workweek(s): earned {earnings} gp at a "
        f"modest lifestyle."
    )
    return DowntimeResult(
        activity="work",
        days=days,
        gold_delta=earnings,
        narration=narration,
        details={
            "workweeks": workweeks,
            "earnings": earnings,
            "lifestyle": "modest",
        },
    )


def train(
    target: str,
    *,
    days: int = WORKWEEK_DAYS,
    progress_before: int = 0,
    target_kind: str = "tool",
) -> DowntimeResult:
    """Resolve a period of Training toward a new language/tool (XGE).

    Training takes 250 days at 1 gp/day. The caller passes cumulative
    ``progress_before`` days; completion grants the proficiency named by
    ``target`` (a tool id or language id; ``target_kind`` disambiguates).
    """
    target = (target or "").strip()
    target_kind = (target_kind or "tool").strip().lower()
    total_days_needed = 250
    cost_per_day = 1

    days = max(0, int(days))
    cumulative = progress_before + days
    complete = cumulative >= total_days_needed
    progress_now = min(cumulative, total_days_needed)
    cost = days * cost_per_day  # gold spent this period

    if complete:
        line = (
            f"Completed training in {target} ({target_kind}). "
            f"You now have proficiency in {target}."
        )
    else:
        remaining = total_days_needed - progress_now
        line = (
            f"Trained in {target} for {days} day(s): {progress_now}/"
            f"{total_days_needed} days ({remaining} to go)."
        )
    return DowntimeResult(
        activity="training",
        days=days,
        gold_delta=-cost,
        narration=line,
        details={
            "target": target,
            "target_kind": target_kind,
            "progress_before": progress_before,
            "days_this_period": days,
            "progress_now": progress_now,
            "total_days_needed": total_days_needed,
            "complete": complete,
            "cost": cost,
        },
    )


def religion(
    *,
    modifier: int = 0,
    dc: int = 15,
    current_exhaustion: int = 0,
    roll: Optional[int] = None,
    roller: Optional[Roller] = None,
) -> DowntimeResult:
    """Resolve a workweek of religious devotion (XGE).

    A successful Religion/Insight check grants a moment of clarity that eases
    one exhaustion level. Costs a small donation (5 gp).
    """
    dc = max(1, int(dc))
    cost = 5
    shown, total, ok = _check(modifier, dc, roll=roll, roller=roller)
    ease = 1 if (ok and current_exhaustion > 0) else 0
    new_exhaustion = max(0, current_exhaustion - ease)
    narration = (
        f"Spent a workweek in devotion (DC {dc} Religion check: rolled {shown} "
        f"→ {'success' if ok else 'failure'}). "
        + (
            f"A moment of clarity eased 1 exhaustion level (now {new_exhaustion})."
            if ease else "No respite came."
        )
    )
    return DowntimeResult(
        activity="religion",
        days=WORKWEEK_DAYS,
        gold_delta=-cost,
        narration=narration,
        details={
            "dc": dc,
            "roll": shown,
            "total": total,
            "success": ok,
            "exhaustion_before": current_exhaustion,
            "exhaustion_after": new_exhaustion,
            "exhaustion_delta": -ease,
            "cost": cost,
        },
    )


# --------------------------------------------------------------------------- #
# DM helpers
# --------------------------------------------------------------------------- #

def downtime_summary_for_dm(activity_id: str) -> str:
    """A one-line DM-ready summary for the activity context block."""
    a = get_activity(activity_id)
    if not a:
        return ""
    source = "PHB" if a.source == "PHB" else "XGE"
    return f"Downtime ({source}): {a.name} — {a.description}"


def resolve(activity_id: str, **kwargs: Any) -> DowntimeResult:
    """Dispatch a downtime resolution by activity id.

    Convenience entry point: maps an ``activity_id`` to the matching resolver,
    passing through keyword arguments. Raises ``ValueError`` for unknown ids.
    """
    a = get_activity(activity_id)
    if not a:
        raise ValueError(f"Unknown downtime activity: {activity_id!r}")

    dispatch = {
        "carousing": carouse,
        "crime": crime,
        "gambling": gamble,
        "pit_fighting": pit_fight,
        "research": research,
        "relaxation": relax,
        "crafting": craft,
        "profession": practice_profession,
        "work": work,
        "training": train,
        "religion": religion,
    }
    fn = dispatch[a.id]
    # Drop caller keys the chosen resolver doesn't accept, for flexibility.
    import inspect
    sig = inspect.signature(fn)
    accepts_kwargs = any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    if accepts_kwargs:
        return fn(**kwargs)
    filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return fn(**filtered)
