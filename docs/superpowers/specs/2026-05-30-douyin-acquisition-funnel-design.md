# DouYin_Spider Acquisition Funnel Design

Date: 2026-05-30
Repo: `/Users/mac/Documents/Codex/2026-05-29/cv-cat-douyin-spider-https-github`
Status: Approved for planning, not yet implemented

## 1. Context

The repository already has a local Web UI and a first-pass keyword funnel page, but the current flow is still crawler-centric:

- it collects by keyword
- it stores raw leads
- it supports later private-message actions

That is not sufficient for the actual business goal. The real goal is to help a Douyin-based companionship/boosting shop find likely paying `Delta Force` customers, not simply gather usernames.

The user clarified the target operating model:

- business focus: `Delta Force` player acquisition
- service mix: all three are needed
  - boosting / carry
  - entertainment companion play
  - fixed team / scheduled sessions
- default business priority: boosting / carry first
- lead-source priority:
  - comments with strong intent first
  - search results second
  - live-room demand as supplemental
- workflow modes required:
  - manual review then outreach
  - scored semi-automatic outreach
  - batch private messaging
- default risk profile: `safe first`

## 2. Goals

The new funnel system should:

- identify likely `Delta Force` customers rather than generic game users
- prioritize users expressing direct demand for help, teammates, companion play, or rank gain
- unify comments, search, and live-derived leads into one scoring pipeline
- support three selectable operating modes:
  - manual review
  - semi-automatic outreach
  - batch outreach
- keep `safe first` as the default operating profile
- track not just lead capture, but outreach and conversion progress

## 3. Constraints

- Reuse existing repository capability layers instead of replacing them.
- Keep the system local-only and operator-facing.
- Preserve raw debugging visibility while the tool remains localhost-only.
- Do not treat every captured user as a customer; scoring and filtering are required.
- Default behavior must favor account safety over maximum outreach volume.

## 4. Business Problem

The current pain is not “no data source exists.” The pain is:

- too many low-value users
- weak separation between viewers and buyers
- no consistent way to rank demand strength
- no operational closed loop from lead capture to conversion result

The system therefore needs to behave like a lightweight acquisition CRM built on top of Douyin collection flows.

## 5. Options Considered

### Option A: raw keyword harvesting and manual screening

Pros:

- fastest to implement
- lowest model complexity
- no scoring system needed

Cons:

- too noisy
- poor operator efficiency
- weak repeatability
- scales badly for a small shop

### Option B: scored lead pool with selectable outreach workflows

Pros:

- matches the real business process
- supports both precision and scale
- keeps operator control
- works with safe-first default behavior
- gives measurable conversion insight

Cons:

- requires explicit scoring rules
- more state and UI than a plain crawler

### Option C: aggressive auto-outreach from all sources

Pros:

- highest immediate throughput

Cons:

- highest account risk
- lowest precision
- easy to annoy low-intent users
- poor fit for the user’s stated default safety preference

### Chosen Option

Option B is the chosen design.

This system should become a `lead acquisition backend`, not merely a `keyword crawler page`.

## 6. Core Operating Model

The funnel is organized as a four-stage pipeline:

1. `Capture`
2. `Intent Scoring`
3. `Outreach Workflow`
4. `Conversion Tracking`

### 6.1 Capture

Lead sources are prioritized as follows:

1. comments with explicit demand language
2. search-derived users and authors
3. live-room demand signals

The system should keep all three sources, but comments are the default top-priority source because direct comment text contains the clearest buying intent.

### 6.2 Intent Scoring

Every captured lead receives a score and grade before outreach.

### 6.3 Outreach Workflow

Each lead can be routed through one of three modes:

- manual review
- scored semi-automatic sending
- batch messaging

The operator chooses the workflow mode per run or per filtered lead set.

### 6.4 Conversion Tracking

Every lead should move through a visible status path:

- `new`
- `reviewing`
- `approved`
- `contacted`
- `replied`
- `added_contact`
- `paid`
- `invalid`

This turns the funnel from “data collection” into “customer acquisition operations.”

## 7. Intent Scoring Design

The scoring model should use a `100-point` structure.

### 7.1 Score Dimensions

- `Demand Expression Score`
  - highest weight
- `Delta Force Relevance Score`
  - confirms the demand belongs to the target game context
- `Payment Likelihood Score`
  - identifies likely buyers rather than casual viewers
- `Reachability / Activity Score`
  - prioritizes active and reachable users
- `Risk Penalty`
  - reduces score for likely同行, ad accounts, studio accounts, or low-quality noise

### 7.2 Demand Signal Tiers

#### Tier A: strongest demand

- `求带`
- `求陪玩`
- `求上分`
- `有没有人带`
- `谁带带我`
- `来个厉害的带我`

#### Tier B: strong supporting demand

- `缺队友`
- `找搭子`
- `找车队`
- `一起打`
- `有没有固定队`

#### Tier C: weaker but still monetizable pain

- `打不上去`
- `卡段位`
- `单排坐牢`
- `太难了`
- `老被虐`

#### Tier D: low-value engagement

- `厉害`
- `牛`
- `哈哈`
- `学到了`

Tier D should not produce high-intent leads by itself.

### 7.3 Delta Force Relevance Signals

Examples of positive relevance terms:

- `三角洲`
- `三角洲行动`
- `段位`
- `上分`
- `带飞`
- `车队`
- `队友`
- `单排`
- `双排`
- `四排`

### 7.4 Payment Likelihood Signals

Examples of higher-value signals:

- `有没有靠谱的`
- `多少钱`
- `想找长期的`
- `有人接吗`
- `晚上带我打`
- `固定队有吗`

### 7.5 Grading

- `S >= 85`
- `A = 70-84`
- `B = 50-69`
- `C < 50`

Default routing:

- `S/A`: recommended outreach pool
- `B`: review-only pool
- `C`: archive-only pool

## 8. Product Surface

The current keyword funnel page should evolve into a dedicated acquisition backend with six major pages.

### 8.1 Dashboard

Purpose:

- show acquisition results, not crawler internals

Metrics:

- leads added today
- `S/A/B/C` counts
- source distribution
- contacted count
- replied count
- added-contact count
- paid count
- risky action count

### 8.2 Capture Tasks

Purpose:

- configure and run acquisition jobs

Controls:

- keyword groups
- source priority
- precision profile
- risk profile
- outreach mode

Task output:

- real-time progress
- current source being processed
- current lead count
- high-intent lead count
- failure step

### 8.3 High-Intent Lead Pool

Purpose:

- serve as the main operator workspace

Each row should show:

- nickname
- `user_id`
- source
- matched keywords/signals
- score and grade
- score reasons
- original comment text or demand text
- source work / source live / source context
- contact status
- reply status
- conversion status
- risk label

Important filters:

- only `S/A`
- comments only
- specific demand phrases
- uncontacted only
- today only
- specific source mode

### 8.4 Outreach Center

Purpose:

- convert approved leads into contact actions

Features:

- message template library
- template recommendation by lead type
- manual send
- semi-automatic send queue
- batch send setup
- send history
- reply tracking

Template families:

- boosting / rank gain
- companion / entertainment
- fixed team / scheduled sessions

### 8.5 Conversion Tracking

Purpose:

- measure what actually produces customers

Views:

- conversion by keyword group
- conversion by source type
- conversion by score grade
- conversion by outreach template

### 8.6 Rules Center

Purpose:

- let operators tune the funnel without code changes

Configurable items:

- keyword groups
- positive intent terms
- exclusion terms
- risk terms
- score weights
- outreach defaults
- daily limits

## 9. Selectable Operating Modes

The system must support all three modes in parallel.

### Mode 1: Manual Review

- leads enter a review queue
- operator checks score reasons and comment text
- operator chooses whether to contact

### Mode 2: Semi-Automatic Outreach

- system prefilters by score
- system recommends a template
- operator confirms before sending

### Mode 3: Batch Messaging

- operator selects a filtered lead set
- system sends within configured limits
- still subject to risk controls

Default mode:

- `Manual Review`

## 10. Precision and Risk Profiles

The system should expose three selectable profiles while defaulting to the safest one.

### 10.1 Precision Profiles

- `少而准`
- `平衡`
- `多而广`

### 10.2 Risk Profiles

- `安全优先`
- `平衡`
- `效率优先`

Default:

- precision: operator-selectable
- risk: `安全优先`

## 11. Default Rules

### 11.1 Default Capture Template

The system should ship with three prebuilt capture templates:

- `精准截流`
- `平衡截流`
- `放量截流`

Default template:

- `精准截流`

### 11.2 Default Outreach Limits

Under `安全优先`, defaults should include:

- single batch send limit: `10`
- daily outreach cap: `30`
- no repeat send to the same user
- no repeat send for the same run
- `B/C` leads blocked from batch mode by default

### 11.3 Default Risk Exclusions

Examples:

- likely同行
- ad or studio accounts
- low-intent interaction-only accounts
- obvious non-target users

## 12. Data Model Additions

The current funnel data model should evolve beyond raw collection state.

### 12.1 Lead-Level Fields

- source type
- source target id
- original text
- matched signals
- score
- grade
- score explanation
- outreach mode
- review status
- contact status
- conversion status
- risk labels

### 12.2 Run-Level Fields

- source mode
- precision profile
- risk profile
- outreach mode
- processed count
- total count
- high-intent count
- contacted count
- replied count

## 13. Real-Time UX Behavior

The acquisition pages should show live operational movement.

Required behavior:

- new task appears immediately after submit
- progress updates automatically
- lead list refreshes without manual reload
- score-driven segmentation becomes visible as rows arrive

The current task and lead regions already support polling in the first implementation pass; the acquisition backend should keep that behavior and expand it with business-state fields.

## 14. Source-Specific Strategy

### 14.1 Comments First

This is the default high-priority acquisition strategy.

Flow:

1. search for Delta Force demand-related works
2. inspect authors
3. inspect comments
4. score comments by intent expression
5. route high-intent users into review or outreach pools

### 14.2 Search Second

Search-derived users are useful when comment density is low or comment APIs are unstable. Search leads should usually score below explicit demand comments unless they contain strong intent text in metadata or recent content context.

### 14.3 Live Supplemental

Live demand is useful for immediate intent, but should remain a supplemental source because it is noisier and more ephemeral.

## 15. Non-Goals

- public SaaS productization
- multi-tenant operator management
- automated follow-up conversation AI
- complete removal of manual judgment
- aggressive default outreach behavior

## 16. Rollout Recommendation

Phase 1 should focus on a stable closed loop:

- capture high-intent leads
- score and grade them
- support manual review
- support semi-automatic send
- track replies and conversions

Phase 2 can expand:

- batch sending controls
- richer score tuning
- live-source expansion
- more advanced operator analytics

## 17. Success Criteria

The design is successful when:

- the operator can reliably produce a daily list of `S/A` Delta Force leads
- comment-driven demand users are easy to identify and inspect
- the operator can choose among manual, semi-automatic, and batch outreach modes
- account-risk controls remain visible and enforceable
- the team can trace which keyword groups and source patterns produce actual paying customers
