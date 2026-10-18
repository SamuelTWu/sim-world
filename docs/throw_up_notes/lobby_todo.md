
## Phase 11: Main Menu and Lobby

### 11.1 Server lobby state

- [ ] 11.1.1 Create `server/lobby.py`:
  ```python
  @dataclass
  class LobbyPlayer: id: str; name: str; ready: bool = False; connected: bool = True
  class Lobby:
      players: dict[str, LobbyPlayer]; host: str | None; settings: dict   # {"seed": int, "gen": {...}}
      def join(pid) -> None; def leave(pid) -> None; def set_ready(pid, v) -> None
      def set_nation(pid, name, color, icon) -> str|None      # returns error code or None
      def set_settings(pid, patch: dict) -> str|None
      def can_start() -> bool;  def snapshot() -> dict
  ```
  Nation data lives in `Nations` (G.2); `Lobby` calls into it. Host is the first joiner. `snapshot()` returns plain dicts and is the only thing sent to clients.
- [ ] 11.1.2 Wire into `Server`: on accepted connection, if `phase == LOBBY` call `lobby.join`; else reply `LOBBY_ERROR game_started` and close. On disconnect call `lobby.leave` and broadcast. Remove partially initialized clients in a `try/finally` around the handshake.
- [ ] 11.1.3 Protocol (`protocol.py`):
  client to server: `LOBBY_SET_NATION {name, color, icon}`, `LOBBY_SET_READY {ready}`, `LOBBY_SET_SETTINGS {seed?, gen?}`, `LOBBY_START {}`.
  server to client: `LOBBY_STATE {players:[{id,name,ready,connected,nation:{name,color,icon}}], host, settings, can_start}`, `LOBBY_ERROR {code, message}`.
  Broadcast the full `LOBBY_STATE` after every accepted change. No deltas.
- [ ] 11.1.4 **Host policy.** If the host leaves, host passes to the earliest remaining joiner (ordered dict). If nobody remains, the server closes (hosted) or stops (local). Broadcast `LOBBY_STATE` with the new host. Test `check_lobby.py` cases: join order, host transfer, last player leaves.

### 11.2 Validation (all in `lobby.py`, pure functions, tested directly)

- [ ] 11.2.1 `valid_nation_name(name, taken)`: strip, 1..24 chars, regex `^[A-Za-z0-9 _'\-]+$`, no leading/trailing spaces, case-insensitive uniqueness against other players' nations, small banned list constant. Return error codes `name_length`, `name_chars`, `name_taken`, `name_banned`.
- [ ] 11.2.2 Colors: choose a server-owned `PALETTE` list and accept an index or exact `#rrggbb` that is in the palette. Reject duplicates with `color_taken`. Icons: `ICONS` list of ids; reject unknown.
- [ ] 11.2.3 Settings: `SETTINGS_SCHEMA = {"seed": (int, 0, 2**31-1), "gen.<field>": (type, min, max), ...}` built from the real `GenerationSettings` fields (inspect them). `set_settings` checks host, phase, key whitelist, type, range; unknown key is an error; apply atomically (all keys valid or none applied).
- [ ] 11.2.4 Ready and start: `LOBBY_SET_READY` any player. `can_start()` = host exists and all connected non-host players ready (policy: host may start only when all others are ready; document in README). `LOBBY_START` host only, phase `LOBBY`, `can_start()`; a second `LOBBY_START` returns `already_started`.
- [ ] 11.2.5 Test `check_lobby.py`: 3 fake clients through the real message handlers; unauthorized settings, bad names, duplicates, disconnect frees name, repeated start, wrong phase. Print the check count.

### 11.3 Client menu and connection

- [ ] 11.3.1 Menu: edit the existing menu module to three buttons `Singleplayer`, `Host Server`, `Join Server`. Menu state machine: `MENU -> CONNECTING -> LOBBY | ERROR(msg) -> MENU`. All buttons disabled in `CONNECTING`.
- [ ] 11.3.2 Local server launcher `server/launcher.py`: `start_local(host="127.0.0.1", port=0) -> LocalServer(port, stop())`. Runs `Server` in a background thread with its own asyncio loop (or a subprocess if the existing server entry point is already a script; follow how `run_server` is currently started). Bind port 0 and read the actual port back. A module-level handle prevents a second local server; `stop()` is idempotent and called on leaving to menu and on exit.
- [ ] 11.3.3 Singleplayer: `start_local` then connect to it as the host. Hosting: same with `0.0.0.0` and a user-supplied port (default constant). Join: parse `host[:port]` (reject empty, bad port), connect with a 5 s timeout.
- [ ] 11.3.4 Errors: map `ConnectionRefusedError`, timeout, DNS failure, protocol mismatch, and `LOBBY_ERROR game_started` to short messages. No tracebacks in the UI. A failed attempt leaves no client thread and no local server running (test with a closed port).
- [ ] 11.3.5 Lobby screen: draw from the latest `LOBBY_STATE` held on the `Client`. Controls send the messages from 11.1.3. Only host sees editable settings and the Start button, others see read-only values. Tutorial popup toggle is local config, never sent.
- [ ] 11.3.6 Test `check_menu_flow.py` (no pygame): drive the menu state machine with a fake connector: success, refused, timeout, double click, mismatch error returns to MENU.
