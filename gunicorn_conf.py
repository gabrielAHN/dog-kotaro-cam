started_capture = False
set_method = False

def on_starting(server):
    global started_capture, set_method
    if not set_method:
        import multiprocessing as mp
        mp.set_start_method('spawn')
        set_method = True
    from dogcam_stream import capture_proc
    if not started_capture and not capture_proc.is_alive():
        capture_proc.start()
        started_capture = True

def on_exit(server):
    from dogcam_stream import capture_proc
    if capture_proc.is_alive():
        capture_proc.terminate()
        capture_proc.join(timeout=5)