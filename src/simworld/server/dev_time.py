MAX_TICKS_PER_LOOP = 4
DEFAULT_SPEED = 1.0


def init_time(server):
    server.paused = False
    server.pending_steps = 0
    server.speed = DEFAULT_SPEED
    server.credit = 0.0


def clear_credit(server):
    server.credit = 0.0


def ticks_to_run(server):
    if server.paused:
        count, server.pending_steps = server.pending_steps, 0
        return count

    server.credit += server.speed
    count = min(int(server.credit), MAX_TICKS_PER_LOOP)
    server.credit -= count
    return count