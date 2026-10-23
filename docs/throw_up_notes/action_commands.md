# Choosing Actions for Pixels

How a player tells pixels what to do. Fast by default (one click for the common case), with more control available when the player wants it. Nothing here needs the player to know an action exists before they see it.

## Goals

- **One click for the common case.** Moving, attacking, picking up and gathering should not need a menu.
- **A menu when there is a choice.** If several actions make sense, show them as a wheel of icons, close to the cursor.
- **Nothing hard-coded.** Every action, its icon, its label and where it applies comes from the action's spec, so new and modded actions show up with no UI changes.
- **Depth is opt-in.** Queues, hotkeys and standing orders exist, but a new player never has to meet them.

## The model in three parts

1. **Smart click:** with pixels selected, right-click a target and the best action for that target happens.
2. **Wheel:** hold the right button (or long-press on touch) on a target and a wheel shows every action the selected pixels can do there. Release on one to choose it.
3. **Action bar:** actions that do not need a target (stop, eat, craft, build menu, return to self-chosen behavior) sit in a bar at the bottom of the screen for the current selection, with hotkeys 1 to 9.

Selecting never opens a popup by itself. A popup on every selection would slow down the most common thing a player does.

## Selecting

- Click a pixel to select it; drag a box or shift-click to select a group (the existing `box` selection).
- Clicking empty ground with nothing to select clears the selection.
- Only the player's own pixels can be commanded.

## Smart click (right-click)

The game asks each action the selected pixels can do whether it applies to what was clicked, and runs the first one that says yes, in priority order. Typical results:

| Click on | Default action |
|---|---|
| Ground or any free tile | move |
| A hostile pixel | attack |
| Water | fish (or move, if nobody selected can fish) |
| An item on the ground | pickup |
| A storage structure | deposit |
| A friendly pixel or structure | the first applicable action (follow, give, repair...) or move next to it |

Each action's spec declares a `click` resolver and a `click_priority` (checklist 15.3). A new action gets smart-click behavior by declaring them. Move is always the last fallback.

## The wheel (hold right-click)

The wheel opens at the cursor and lists the actions that apply to what is under it.

- **Contents:** every action that at least one selected pixel can perform on that target. The target can be a tile, a pixel, a structure or a point.
- **Order:** by `click_priority`, so the action smart click would have used is in the top slot. A move of the mouse toward a slot highlights it; releasing chooses it.
- **Size:** up to 8 slots. If there are more, a "..." slot opens a second ring.
- **Groups:** each slot shows how many of the selected pixels can do it (for example `3/5`). Choosing it orders only those pixels; the rest ignore it. This matches how box commands already filter by "can do this action".
- **Greyed entries:** an action that applies to the target but that nobody selected can do (missing item, missing ability) is shown greyed, with the reason on hover. Hidden entirely would hide what the player could unlock.
- **Remembered choice:** the last action chosen for a kind of target moves toward the top slot, so repeated work gets faster.

## The action bar (no target needed)

For the current selection, a bar shows actions that do not involve a point or a target: stop, eat, craft (opens the recipe book), build (opens the blueprint picker), and "go back to self-chosen behavior". The bar shows the actions that at least one selected pixel can do, with the same `3/5` count on groups. Hotkeys 1 to 9 trigger them in order.

## Actions that need more than a target

Some actions need one more choice (how many to craft, which blueprint to build). Choosing them from the wheel or bar opens a small picker next to the cursor, and confirming it sends the order. This is the only extra step in the whole flow.

## Feedback

- A marker is drawn at the target and a thin line to each ordered pixel for a moment.
- A pixel's current action and phase are shown over it ("walking to water", "fishing").
- If an order cannot be done, the player gets a short message with the reason (the failure codes from the action pipeline).
- A pixel with an order is not interrupted by its own decisions; a new order replaces the old one; `stop` returns it to self-chosen behavior.

## Where the data comes from

- The server sends each pixel's commandable actions with their name, label, icon and argument schema (the abilities message, checklist 15.4). The client builds the wheel and the bar from that list; it contains no action names.
- A click is resolved on the server with the action's `click` resolver, so what the client shows and what the server will accept cannot disagree.
- The order itself is the one pixel command (`do`, checklist 15.1): ids or box, action name, data.

## Advanced options (off by default)

These are opt-in and add no steps for a new player.

- **Queue:** hold shift while choosing to add the action to the end of the pixel's queue instead of replacing the current one. (Needs `entity.task` to become a list; the pipeline allows it later.)
- **Custom hotkeys:** bind any action to a key from the action bar settings.
- **Default action override:** choose what smart click does for a kind of target (for example right-click on water always means move).
- **Standing orders:** mark a pixel or group as "work this area" or "auto craft this"; this builds on work orders and autonomous actions, not on the click flow.
- **Always-wheel setting:** open the wheel on every right-click instead of on hold, for players who prefer menus.

## Build order

1. The abilities list on the server and the `click` resolvers (15.3 and 15.4).
2. Smart click for move, attack and pickup.
3. The wheel (hold to open, slots from the abilities list, group counts, greyed entries).
4. The action bar and hotkeys.
5. The small picker for actions with extra arguments.
6. Feedback: target marker, order lines, action text over pixels, failure messages.
7. Advanced options, one at a time.

Steps 1 to 3 give the whole core experience.

## Open questions

- Should the wheel open on hold or on a second click? (The plan assumes hold, with an always-wheel setting.)
- Should greyed actions show for everyone or only after the first time the player sees the ability?
- Does left-click stay select-only, or can it also place or confirm in some modes (build placement, picker confirmation)?