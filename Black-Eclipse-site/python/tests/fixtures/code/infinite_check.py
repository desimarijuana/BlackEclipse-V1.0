"""An infinite-loop fixture: must be killed by the timeout, no orphan."""
print("starting infinite loop", flush=True)
while True:
    pass
